import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import pandas as pd
import time
import os
import re
import PyPDF2

# 1. 페이지 설정: 중앙 정렬 레이아웃 고정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 및 가독성 최적화 커스텀 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 750px !important; padding-top: 5rem !important; }

    /* [로그인 화면] 카드 스타일 및 파란 박스 가독성 */
    div[data-testid="stForm"] {
        background-color: #ffffff !important;
        padding: 45px !important;
        border-radius: 20px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05) !important;
        border: 1px solid #e1e4e8 !important;
        text-align: center;
    }
    div[data-testid="stNotification"] {
        font-size: 16px !important;
        line-height: 1.6 !important;
        background-color: #f0f7ff !important;
        border-radius: 12px !important;
        color: #0056b3 !important;
        padding: 20px !important;
    }

    /* [사이드바] 개별 박스 스타일 및 버튼 레이아웃 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    .sidebar-user-box {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #edf0f2;
        margin-bottom: 20px;
        text-align: center;
    }
    div[data-testid="stSidebar"] .stButton > button {
        background-color: #ffffff !important;
        border: 1px solid #e9ecef !important;
        padding: 18px 15px !important;
        border-radius: 15px !important;
        width: 100% !important;
        margin-bottom: -5px !important;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p {
        font-size: 13px !important; color: #666 !important; line-height: 1.5 !important;
        white-space: pre-line !important; text-align: left !important; margin: 0 !important;
    }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p::first-line {
        font-size: 16px !important; font-weight: 700 !important; color: #1a1c1e !important;
    }

    /* 상담 중 버튼 비활성화 스타일 */
    div[data-testid="stSidebar"] .stButton > button:disabled {
        background-color: #f0f0f0 !important;
        color: #aaa !important;
    }

    /* [메인화면] 플랫 디자인 인사말 */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; background-color: transparent !important; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 21px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 데이터 로드 (KCIM 1990년 창립 및 HR팀 정보 반영)
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
                db[name] = {"pw": phone[-4:], "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [2] 유틸리티 기능 (KST 시간, 요약 로직)
# --------------------------------------------------------------------------
def get_kst_now():
    """서버 시간 무관 한국 표준시(KST) 반환"""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

def summarize_text(text):
    """시트 기록용 1문장 핵심 요약 로직"""
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "질문이나 답변 내용을 스프레드시트 기록용으로 아주 짧게 1문장 요약해줘."}, {"role": "user", "content": text}],
            temperature=0
        )
        return res.choices[0].message.content.strip()
    except: return text[:50] + "..."

def save_to_sheet(dept, name, rank, category, question, answer, status):
    """구글 시트 실시간 기록"""
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("응답시트")
        # H열(처리결과)에 '담당자 확인 필요' 자동 기입 포함
        sheet.append_row([get_kst_now(), dept, name, rank, category, question, answer, status])
    except: pass

def get_dynamic_greeting():
    """접속 시간대별 맞춤형 인사말 생성"""
    kst = timezone(timedelta(hours=9))
    now_hour = datetime.now(kst).hour
    if 5 <= now_hour < 11: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 11 <= now_hour < 14: return "즐거운 점심시간입니다. 맛있는 식사 하셨나요? 🍱"
    elif 14 <= now_hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    elif 18 <= now_hour < 22: return "오늘 하루도 고생 많으셨습니다! 마무리하며 도와드릴 일이 있을까요? ✨"
    else: return "늦은 시간까지 수고가 많으시네요. 무엇을 도와드릴까요? 🌙"

# --------------------------------------------------------------------------
# [3] 초기화 및 상태 관리
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

def reset_chat():
    st.session_state["inquiry_active"] = False
    st.session_state["messages"] = []
    st.rerun()

# --------------------------------------------------------------------------
# [4] UI 및 대화 로직
# --------------------------------------------------------------------------
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        input_name = st.text_input("성명", placeholder="이름을 입력하세요")
        input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {**EMPLOYEE_DB[input_name], "name": input_name}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")

else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>{user['dept']}</span></div>", unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "사옥·차량 유지보수, 장비 교체 및 수리 요청"), ("👤 입퇴사/이동", "제증명 발급, 인사 발령, 근무 확인 및 채용"), ("📋 프로세스/규정", "사내 규정 안내, 시스템 사용 이슈 및 보안 문의"), ("🎁 복지/휴가", "경조사, 지원금, 교육 지원 및 동호회 활동"), ("📢 불편사항", "근무 환경 내 불편 및 피해 사항 컴플레인"), ("💬 일반/기타", "단순 질의, 일반 업무 협조 및 기타 문의")]
        
        for title, desc in cats:
            if st.button(f"{title}\n{desc}", key=title, disabled=st.session_state["inquiry_active"]):
                st.session_state["inquiry_active"] = True
                st.session_state.messages.append({"role": "assistant", "content": f"[{title}] 주제에 대해 상담을 시작합니다. 무엇을 도와드릴까요?"})
                st.rerun()
        
        st.markdown("---")
        if st.session_state["inquiry_active"]:
            if st.button("✅ 현재 상담 종료하기", use_container_width=True): reset_chat()
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    if not st.session_state.messages:
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']} {user['rank']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{get_dynamic_greeting()}</p></div>", unsafe_allow_html=True)
    
    # [수정] 대화 기록 출력 (누락 방지)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    # 채팅 입력 및 저장 처리
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state["inquiry_active"] = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        # [수정] '인사부' -> 'HR팀' 명칭 변경 및 요약 지침 강화
        sys_msg = f"너는 1990년 창립된 KCIM의 전문 HR팀 매니저야. {user['name']}님께 정중하게 답변해줘. 시설 수리, 차량/숙소 예약 등 실무 처리가 필요한 건은 답변 끝에 반드시 [ACTION]을 붙여줘. 마지막엔 반드시 [CATEGORY:분류명]을 포함해줘."
        
        with st.spinner("KCIM 매니저가 답변을 작성 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                answer = res.choices[0].message.content
                
                # 자동 분류 및 태그 제거
                status = "담당자 확인 필요" if "[ACTION]" in answer else "처리완료"
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "일반/기타"
                clean_ans = answer.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
                
                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                
                # [수정] 질문 및 답변 요약 후 시트 기록
                q_summary = summarize_text(prompt)
                a_summary = summarize_text(clean_ans)
                save_to_sheet(user['dept'], user['name'], user['rank'], category, q_summary, a_summary, status)
                st.rerun()
            except: pass
