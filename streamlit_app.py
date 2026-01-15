import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
import re

# 1. 페이지 설정: 중앙 정렬 레이아웃 및 타이틀 고정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 및 여백 최적화 커스텀 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }
    
    /* 로그인/알림 디자인 */
    div[data-testid="stForm"] { background-color: #ffffff; padding: 50px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; text-align: center; }
    div[data-testid="stNotification"] { font-size: 16px; background-color: #f0f7ff; border-radius: 12px; color: #0056b3; padding: 20px; }
    
    /* 사이드바 및 로고 중앙 정렬 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    .sidebar-user-box { background-color: #f8f9fa; padding: 20px; border-radius: 15px; border: 1px solid #edf0f2; margin-bottom: 20px; text-align: center; }
    
    /* 카테고리 버튼 가독성 고정 */
    div[data-testid="stSidebar"] .stButton > button { background-color: #ffffff !important; border: 1px solid #e9ecef !important; padding: 18px 15px !important; border-radius: 15px !important; width: 100% !important; margin-bottom: -5px !important; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p { font-size: 13px; color: #666; line-height: 1.5; white-space: pre-line; text-align: left; margin: 0; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p::first-line { font-size: 16px; font-weight: 700; color: #1a1c1e; }
    
    /* 안내 문구 상단 여백 확대 */
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 60px !important; line-height: 1.6; }

    /* 중앙 플랫 인사말 디자인 */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 23px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 규정 파일 지식 베이스 맵핑
# --------------------------------------------------------------------------
COMPANY_DOCUMENTS_INFO = """
[KCIM 최신 사내 규정 파일 지식]
1. 2025년_복지제도.pdf: 연차, Refresh 휴가, 자녀 학자금 등 복합
2. 2025년 달라지는 육아지원제도.pdf: 육아휴직, 단축근무, 모성보호 등
3. 2025_현장근무지원금_최종.pdf: 식대, 교통비, 원거리 지원금 지침
... (이하 17종 규정 목록 유지) ...
"""

# --------------------------------------------------------------------------
# [2] 유틸리티 기능 (KST 보정, 요약, 시트 저장)
# --------------------------------------------------------------------------
def get_kst_now():
    """한국 표준시(KST) 반환"""
    return datetime.now(timezone(timedelta(hours=9)))

def summarize_text(text):
    """시트 기록용 핵심 요약 (정상 기록 복구)"""
    if not text or len(text.strip()) == 0: return "-"
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 전문 요약가야. 입력받은 문장을 한 줄의 핵심 요약문(15자 이내)으로 변환해줘."},
                {"role": "user", "content": text}
            ],
            temperature=0
        )
        return res.choices[0].message.content.strip()
    except: return text[:30] + "..."

def save_to_sheet(dept, name, rank, category, question, answer, status):
    """구글 시트 저장"""
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("응답시트")
        sheet.append_row([get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status])
    except: pass

# --------------------------------------------------------------------------
# [3] 데이터 로드 (KICM 1990년 창립 반영)
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
                db[name] = {"pw": str(row['휴대폰 번호'])[-4:], "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [4] UI 및 대화 실행 로직 (답변 표시 오류 해결)
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

if not st.session_state["logged_in"]:
    # 로그인 폼 (기존과 동일)
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        input_name = st.text_input("성명")
        input_pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {**EMPLOYEE_DB[input_name], "name": input_name}
                st.rerun()

else:
    user = st.session_state["user_info"]
    with st.sidebar:
        # 로고 중앙 정렬
        st.markdown("<div style='text-align: center; width: 100%;'><h2 style='color: #1a1c1e; margin-bottom: 20px;'>🏢 KCIM</h2></div>", unsafe_allow_html=True)
        # HR팀 명칭 반영
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>{user['dept']}</span></div>", unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "사옥·차량 유지보수, 장비 교체 및 수리 요청"), ("👤 입퇴사/이동", "제증명 발급, 인사 발령, 근무 확인 및 채용"), ("📋 프로세스/규정", "사내 규정 안내, 시스템 이슈 및 보안 문의"), ("🎁 복지/휴가", "경조사, 지원금, 교육 지원 및 동호회 활동"), ("📢 불편사항", "근무 환경 내 불편 및 피해 사항 컴플레인"), ("💬 일반/기타", "단순 질의, 일반 업무 협조 및 기타 문의")]
        
        for title, desc in cats:
            if st.button(f"{title}\n{desc}", key=title, disabled=st.session_state["inquiry_active"]):
                st.session_state["inquiry_active"] = True
                st.session_state.messages.append({"role": "assistant", "content": f"[{title}] 주제에 대해 상담을 시작합니다. 무엇을 도와드릴까요?"})
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 안전하게 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.markdown("<p class='beta-notice'> ※ 이 챗봇은 현재 베타 테스트중입니다.<br>오류가 많아도 이해 바랍니다:)</p>", unsafe_allow_html=True)

    # 대화창 렌더링
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    # 채팅 입력 및 [핵심] 답변 즉시 표시 로직
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state["inquiry_active"] = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        # 시스템 페르소나
        sys_msg = f"너는 1990년 창립된 KCIM의 HR팀 매니저야. {user['name']}님께 정중히 답변해줘. 시설 수리 등 실무 확인 건은 끝에 반드시 [ACTION]을 붙여줘. 마지막엔 [CATEGORY:분류명]을 포함해줘."
        
        with st.spinner("KCIM 매니저가 규정을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                answer = res.choices[0].message.content
                
                # 분류 가공
                status = "담당자 확인 필요" if "[ACTION]" in answer else "처리완료"
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "일반/기타"
                clean_ans = answer.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
                
                # [수정] 화면에 즉시 출력하여 지연 현상 해결
                with st.chat_message("assistant"):
                    st.write(clean_ans)
                
                # 세션 상태 업데이트
                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                
                # [수정] 시트 저장 시 질문/답변 요약 기능 적용
                q_summary = summarize_text(prompt)
                a_summary = summarize_text(clean_ans)
                save_to_sheet(user['dept'], user['name'], user['rank'], category, q_summary, a_summary, status)
                
                # 최종 화면 갱신
                st.rerun() 
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
