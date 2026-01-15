import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
import time
import os
import re
import PyPDF2

# 1. 페이지 설정: 중앙 정렬 레이아웃 및 타이틀 고정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 및 가독성 최적화 커스텀 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }

    /* [로그인 화면] 카드 스타일 및 파란 박스 가독성 */
    div[data-testid="stForm"] {
        background-color: #ffffff !important;
        padding: 50px !important;
        border-radius: 20px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05) !important;
        border: 1px solid #e1e4e8 !important;
        text-align: center;
    }
    div[data-testid="stNotification"] {
        font-size: 17px !important;
        line-height: 1.6 !important;
        background-color: #f0f7ff !important;
        border-radius: 12px !important;
        color: #0056b3 !important;
        padding: 20px !important;
    }

    /* [사이드바] 버튼 및 카드 스타일링 */
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
    }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p {
        font-size: 13px !important; color: #666 !important; line-height: 1.5 !important;
        white-space: pre-line !important; text-align: left !important; margin: 0 !important;
    }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p::first-line {
        font-size: 16px !important; font-weight: 700 !important; color: #1a1c1e !important;
    }

    /* [메인화면] 플랫 디자인 인사말 (박스 제거) */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 23px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 데이터 로드 (KCIM 1990년 창립 및 HR 매니저 직무 반영)
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
                db[name] = {"pw": phone[-4:] if len(phone) >= 4 else "0000", 
                            "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

CATEGORY_GREETINGS = {
    "🛠️ 시설/수리": "시설 및 장비 수리가 필요하신가요? 어떤 부분에 도움이 필요하신지 말씀해 주세요. 🛠️",
    "👤 입퇴사/이동": "증명서 발급이나 인사 관련 문의가 있으시군요. 어떤 서류나 절차가 궁금하신가요? 👤",
    "📋 프로세스/규정": "규정이나 시스템 사용법에 대해 안내해 드릴게요. 무엇이 궁금하신가요? 📋",
    "🎁 복지/휴가": "복지나 휴가 제도는 임직원의 소중한 권리입니다. 어떤 혜택에 대해 알고 싶으신가요? 🎁",
    "📢 불편사항": "근무 중 불편한 점이 있으셨군요. 말씀해 주시면 신속히 확인하여 개선하도록 노력하겠습니다. 📢",
    "💬 일반/기타": "기타 궁금하신 사항이나 업무 협조가 필요한 부분이 있다면 편하게 말씀해 주세요. 💬"
}

# --------------------------------------------------------------------------
# [2] 초기화 및 상태 관리
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

def reset_chat():
    st.session_state["inquiry_active"] = False
    st.session_state["messages"] = []
    st.rerun()

# --------------------------------------------------------------------------
# [3] UI 실행 로직
# --------------------------------------------------------------------------

if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold; color: #555;'>🔒 임직원 신원확인</p>", unsafe_allow_html=True)
        input_name = st.text_input("성명", placeholder="성함을 입력하세요")
        input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = EMPLOYEE_DB[input_name]
                st.session_state["user_info"]["name"] = input_name
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")

else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown(f"""<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>{user['dept']}</span></div>""", unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "사옥·차량 유지보수, 장비 교체 및 수리 요청"), ("👤 입퇴사/이동", "제증명 발급, 인사 발령, 근무 확인 및 채용"), ("📋 프로세스/규정", "사내 규정 안내, 시스템 사용 이슈 및 보안 문의"), ("🎁 복지/휴가", "경조사, 지원금, 교육 지원 및 동호회 활동"), ("📢 불편사항", "근무 환경 내 불편 및 피해 사항 컴플레인"), ("💬 일반/기타", "단순 질의, 일반 업무 협조 및 기타 문의")]
        
        for title, desc in cats:
            if st.button(f"{title}\n{desc}", key=title, disabled=st.session_state["inquiry_active"]):
                st.session_state["inquiry_active"] = True
                st.session_state.messages.append({"role": "assistant", "content": CATEGORY_GREETINGS.get(title)})
                st.rerun()
        
        st.markdown("---")
        if st.session_state["inquiry_active"]:
            if st.button("✅ 현재 상담 종료하기", use_container_width=True): reset_chat()
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 메인 인삿말
    if not st.session_state.messages:
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']} {user['rank']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>복지, 규정, 시설 문의 등 무엇을 도와드릴까요?</p></div>", unsafe_allow_html=True)
    
    # 대화 내용 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    # 채팅 입력 및 답변 생성 (SyntaxError 수정 완료)
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state["inquiry_active"] = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        # 시스템 지침 (1990년 창립 KCIM 전문 HR 매니저 페르소나)
        sys_msg = f"너는 1990년 창립된 KCIM의 전문 HR 매니저야. {user['name']}님께 정중하게 답변해줘."
        
        with st.spinner("KCIM 매니저가 답변을 작성 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages
                )
                answer = response.choices[0].message.content
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.rerun()
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
