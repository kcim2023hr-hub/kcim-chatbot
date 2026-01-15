import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
import re
import json

# 실시간 웹 검색 라이브러리 (오류 방지 예외 처리)
try:
    from duckduckgo_search import DDGS
    SEARCH_AVAILABLE = True
except ImportError:
    SEARCH_AVAILABLE = False

# 1. 페이지 설정: 중앙 정렬 레이아웃 및 타이틀 고정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 및 여백 최적화 커스텀 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }
    
    /* 로그인 폼 카드 스타일 */
    div[data-testid="stForm"] { background-color: #ffffff; padding: 50px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; text-align: center; }
    div[data-testid="stNotification"] { font-size: 16px; background-color: #f0f7ff; border-radius: 12px; color: #0056b3; padding: 20px; }
    
    /* 사이드바 디자인 및 로고 중앙 정렬 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    .sidebar-user-box { background-color: #f8f9fa; padding: 20px; border-radius: 15px; border: 1px solid #edf0f2; margin-bottom: 20px; text-align: center; }
    
    /* 카테고리 버튼 가독성 고정 */
    div[data-testid="stSidebar"] .stButton > button { background-color: #ffffff !important; border: 1px solid #e9ecef !important; padding: 18px 15px !important; border-radius: 15px !important; width: 100% !important; margin-bottom: -5px !important; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p { font-size: 13px; color: #666; line-height: 1.5; white-space: pre-line; text-align: left; margin: 0; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p::first-line { font-size: 16px; font-weight: 700; color: #1a1c1e; }
    
    /* 베타 테스트 안내 문구 상단 여백 확대 */
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 60px !important; line-height: 1.6; }

    /* 중앙 플랫 인사말 디자인 */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 21px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 규정 파일 지식 베이스 및 다운로드 리스트
# --------------------------------------------------------------------------
COMPANY_DOCUMENTS_INFO = """
[KCIM 사내 규정 파일 목록]
1. 2025년_복지제도.pdf, 2. 2025년 달라지는 육아지원제도.pdf, 3. 2025_현장근무지원금_최종.pdf
4. 사고발생처리 매뉴얼.pdf, 5. 행동규범.pdf, 6. 취업규칙_2025.pdf
7. 노동부 지원금 매뉴얼.pdf, 8. KCIM 계약서 검토 프로세스.pdf, 9. 2024 재택근무 내부프로세스.pdf
10. 2024_재택근무_운영규정.pdf, 11. 연차유예 및 대체휴가 지침.pdf, 12. 임직원 연락망_2025.pdf
13. 도서구입 및 도서관 운영지침.docx, 14. 사내동호회운영규정.pdf, 15. 사내 와이파이 정보.pdf
16. 2023_KCIM_사내도서지원.pptx, 17. 경영관리본부 업무분장표.pdf
"""

RULES_FILES = [
    "2025년_복지제도.pdf", "2025년 달라지는 육아지원제도.pdf", "2025_현장근무지원금_최종.pdf",
    "사고발생처리 매뉴얼.pdf", "행동규범.pdf", "취업규칙_2025.pdf", "노동부 지원금 매뉴얼.pdf",
    "KCIM 계약서 검토 프로세스.pdf", "2024 재택근무 내부프로세스.pdf", "2024_재택근무_운영규정.pdf",
    "연차유예 및 대체휴가 지침.pdf", "임직원 연락망_2025.pdf", "도서구입 및 도서관 운영지침.docx",
    "사내동호회운영규정.pdf", "사내 와이파이 정보.pdf", "2023_KCIM_사내도서지원.pptx",
    "경영관리본부 업무분장표.pdf"
]

# --------------------------------------------------------------------------
# [2] 유틸리티 및 학습 기능
# --------------------------------------------------------------------------
def get_kst_now():
    """한국 표준시(KST) 반환"""
    return datetime.now(timezone(timedelta(hours=9)))

def search_web(query):
    """실시간 웹 검색"""
    if not SEARCH_AVAILABLE: return "검색 라이브러리 설치 대기 중..."
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
            return str(results)
    except: return "검색 결과가 없습니다."

def summarize_text(text):
    """시트 기록용 요약"""
    if not text: return "-"
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "15자 이내 한 줄 요약."}], temperature=0)
        return res.choices[0].message.content.strip()
    except: return text[:20] + "..."

def save_to_sheet(dept, name, rank, category, question, answer, status):
    """민원 응답 시트 저장"""
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("응답시트")
        sheet.append_row([get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status])
    except: pass

def save_learned_data(name, info):
    """새로 학습한 지식 저장 [학습 기능]"""
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("학습데이터")
        sheet.append_row([get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), name, info])
    except: pass

def load_learned_data():
    """누적된 학습 지식 로드"""
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("학습데이터")
        data = sheet.get_all_records()
        if not data: return ""
        learned_str = "\n[임직원으로부터 학습한 추가 지식]\n"
        for row in data: learned_str += f"- {row['학습내용']}\n"
        return learned_str
    except: return ""

# --------------------------------------------------------------------------
# [3] 데이터 로드 (KICM 인사 데이터)
# --------------------------------------------------------------------------
@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {"관리자": {"pw": "1323", "dept": "HR팀", "rank": "매니저"}}
    if os.path.exists(file_name):
        try:
            df = pd.read_excel(file_name, engine='openpyxl')
            for _, row in df.iterrows():
                name = str(row['이름']).strip()
                phone = re.sub(r'[^0-9]', '', str(row['휴대폰 번호']))
                db[name] = {"pw": phone[-4:] if len(phone)>=4 else "0000", "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [4] 메인 UI 실행
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        input_name = st.text_input("성명", placeholder="이름 입력")
        input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {**EMPLOYEE_DB[input_name], "name": input_name}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")

else:
    user = st.session_state["user_info"]
    learned_knowledge = load_learned_data() # 학습 지식 로드
    
    with st.sidebar:
        st.markdown("<div style='text-align: center; width: 100%;'><h2 style='color: #1a1c1e; margin-bottom: 20px;'>🏢 KCIM</h2></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>HR팀</span></div>", unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "유지보수 요청"), ("👤 입퇴사/이동", "인사 발령/채용"), ("📋 프로세스/규정", "사내 규정 문의"), ("🎁 복지/휴가", "경조사/지원금"), ("📢 불편사항", "근무 환경 불만"), ("💬 일반/기타", "업무 협조 및 기타")]
        for title, desc in cats:
            if st.button(f"{title}\n{desc}", key=title, disabled=st.session_state["inquiry_active"]):
                st.session_state["inquiry_active"] = True
                st.session_state.messages.append({"role": "assistant", "content": f"[{title}] 주제에 대해 상담을 시작합니다. 무엇을 도와드릴까요?"})
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.session_state["inquiry_active"]:
            if st.button("✅ 현재 상담 종료하기", use_container_width=True):
                st.session_state["inquiry_active"] = False
                st.session_state["messages"] = []
                st.rerun()
        if st.button("🚪 안전하게 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.markdown("<p class='beta-notice'>※이 챗봇은 현재 베타 테스트중입니다.<br>오류가 많아도 이해 바랍니다.:)</p>", unsafe_allow_html=True)

    # 대화창 및 인사말
    if not st.session_state.messages:
        now_h = get_kst_now().hour
        greeting = "좋은 아침입니다! ☀️" if 5<=now_h<11 else "맛있는 식사 하셨나요? 🍱" if 11<=now_h<14 else "즐거운 오후입니다! ☕" if 14<=now_h<18 else "오늘 하루 고생 많으셨습니다! ✨"
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']} {user['rank']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{greeting}</p></div>", unsafe_allow_html=True)
    
    for msg in st.session_state.messages:
        if isinstance(msg, dict):
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg["role"] == "assistant":
                    for f_name in RULES_FILES:
                        if f_name in msg["content"] and os.path.exists(f"rules/{f_name}"):
                            with open(f"rules/{f_name}", "rb") as f:
                                st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"dl_{f_name}_{msg['content'][:10]}")

    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state["inquiry_active"] = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        sys_msg = f"""너는 1990년 창립된 KCIM의 HR팀 매니저야. {user['name']}님께 정중히 답변해줘.
        [지식 소스]
        1. 사내 규정: {COMPANY_DOCUMENTS_INFO}
        2. 학습된 추가 지식: {learned_knowledge}
        
        [학습 지침]
        - 질문자가 새로운 정책이나 정보를 알려주면 "학습했습니다"라고 답하고 마지막에 반드시 [LEARN: 학습한 내용]을 포함해줘.
        - 외부 최신 정보가 필요하면 'search_web'을 사용해.
        - 실무 확인 건은 [ACTION], 마지막엔 [CATEGORY:분류명]을 포함해.
        """
        
        with st.spinner("KCIM 매니저가 지식을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                tools = [{"type": "function", "function": {"name": "search_web", "description": "실시간 정보 검색", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}]
                
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + [m for m in st.session_state.messages if isinstance(m, dict)], tools=tools)
                
                if res.choices[0].message.tool_calls:
                    tool_call = res.choices[0].message.tool_calls[0]
                    query = json.loads(tool_call.function.arguments)["query"]
                    search_res = search_web(query)
                    st.session_state.messages.append(res.choices[0].message)
                    st.session_state.messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": search_res})
                    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + [m for m in st.session_state.messages if isinstance(m, dict)])
                
                full_ans = res.choices[0].message.content
                
                # 학습 데이터 처리 [학습 기능]
                if "[LEARN:" in full_ans:
                    learn_fact = re.search(r'\[LEARN:(.*?)\]', full_ans).group(1)
                    save_learned_data(user['name'], learn_fact)
                    full_ans = full_ans.replace(f"[LEARN:{learn_fact}]", "").strip()
                
                status = "담당자 확인 필요" if "[ACTION]" in full_ans else "처리완료"
                category = re.search(r'\[CATEGORY:(.*?)\]', full_ans).group(1) if "[CATEGORY:" in full_ans else "일반/기타"
                clean_ans = full_ans.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
                
                with st.chat_message("assistant"):
                    st.write(clean_ans)
                    for f_name in RULES_FILES:
                        if f_name in clean_ans and os.path.exists(f"rules/{f_name}"):
                            with open(f"rules/{f_name}", "rb") as f:
                                st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"new_dl_{f_name}")

                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                save_to_sheet(user['dept'], user['name'], user['rank'], category, summarize_text(prompt), summarize_text(clean_ans), status)
                st.rerun() 
            except Exception as e: st.error(f"오류: {e}")
