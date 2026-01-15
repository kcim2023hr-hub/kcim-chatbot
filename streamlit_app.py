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

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 및 버튼 스타일 최적화 커스텀 CSS ---
st.markdown("""
    <style>
    /* 전체 배경 및 레이아웃 */
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 750px !important; padding-top: 5rem !important; }

    /* [로그인 화면] 카드 스타일 */
    div[data-testid="stForm"] {
        background-color: #ffffff !important;
        padding: 45px !important;
        border-radius: 20px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05) !important;
        border: 1px solid #e1e4e8 !important;
        text-align: center;
    }

    /* 파란색 안내 박스 */
    div[data-testid="stNotification"] {
        font-size: 16px !important;
        background-color: #f0f7ff !important;
        border-radius: 12px !important;
        color: #0056b3 !important;
    }

    /* [사이드바] 버튼을 카드처럼 스타일링 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    
    /* 사이드바 박스형 정보창 */
    .sidebar-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
        margin-bottom: 12px;
        text-align: center;
    }

    /* 카테고리 클릭 버튼 스타일 최적화 */
    div[data-testid="stSidebar"] .stButton > button {
        background-color: #ffffff !important;
        color: #1a1c1e !important;
        border: 1px solid #e9ecef !important;
        padding: 12px !important;
        border-radius: 12px !important;
        text-align: left !important;
        width: 100% !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03) !important;
        transition: all 0.2s ease !important;
        margin-bottom: -10px !important;
    }
    div[data-testid="stSidebar"] .stButton > button:hover {
        border-color: #28a745 !important;
        background-color: #f8fff9 !important;
    }

    /* [메인화면] 플랫 디자인 고정 */
    .greeting-container { text-align: center; margin-bottom: 40px; padding: 20px 0; }
    .greeting-title { font-size: 34px !important; font-weight: 800; color: #1a1c1e; }
    .greeting-subtitle { font-size: 21px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 데이터 로드 로직 (Saved Info 반영)
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

# 업무 분장 데이터 (이경한 매니저 업무 중심)
WORK_DISTRIBUTION = """
- 이경한 매니저: 사옥/법인차량 관리, 현장 숙소 관리, 근태 관리, 행사 기획/실행, 임직원 제도 수립
- 기타 부서원 업무: 교육, 채용, 비용 처리 등
"""

# --------------------------------------------------------------------------
# [2] 유틸리티 및 시간대 인사말
# --------------------------------------------------------------------------

def get_dynamic_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 12 <= hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    else: return "오늘 하루도 고생 많으셨습니다. 마무리하며 도와드릴 일이 있을까요? ✨"

# --------------------------------------------------------------------------
# [3] 메인 로직 및 카테고리 클릭 이벤트
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []

# [로그인 화면]
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold; margin-bottom: 25px;'>🔒 임직원 신원확인</p>", unsafe_allow_html=True)
        input_name = st.text_input("성명", placeholder="이름 입력")
        input_pw = st.text_input("비밀번호", type="password", placeholder="****")
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = EMPLOYEE_DB[input_name]
                st.session_state["user_info"]["name"] = input_name
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='sidebar-card'>
            <small style='color: #6c757d;'>인증된 사용자</small><br>
            <b style='font-size: 19px;'>{user['name']} {user['rank']}</b><br>
            <span style='color: #28a745; font-weight: 600;'>{user['dept']}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        
        # 카테고리 클릭 시 대화 시작을 위한 버튼 리스트
        cats = [
            ("🛠️ 시설/수리", "사옥·차량 유지보수, 장비 교체 및 수리 요청"),
            ("👤 입퇴사/이동", "제증명 발급, 인사 발령, 근무 확인 및 채용"),
            ("📋 프로세스/규정", "사내 규정 안내, 시스템 이슈 및 보안 문의"),
            ("🎁 복지/휴가", "경조사, 지원금, 교육 지원 및 동호회 활동"),
            ("📢 불편사항", "근무 환경 내 불편 및 피해 사항 컴플레인"),
            ("💬 일반/기타", "단순 질의, 일반 업무 협조 및 기타 문의")
        ]
        
        for title, desc in cats:
            # 버튼 클릭 시 해당 카테고리 주제를 세션 상태에 저장
            if st.button(f"**{title}**\n\n{desc}", key=title):
                st.session_state.messages.append({"role": "user", "content": f"[{title}] 주제에 대해 문의하고 싶습니다."})
                # 즉시 답변 생성을 위해 처리 로직 필요 (아래 chat_input에서 처리)

        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 메인 인삿말 (최초 접속 시에만 표시)
    if not st.session_state.messages:
        greeting_html = f"""
        <div class='greeting-container'>
            <p class="greeting-title">{user['name']} {user['rank']}님, 반갑습니다! 👋</p>
            <p class="greeting-subtitle">{get_dynamic_greeting()}</p>
        </div>
        """
        st.markdown(greeting_html, unsafe_allow_html=True)
    
    # 대화 기록 렌더링
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 채팅 입력 및 처리
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun() # 화면 갱신

    # 자동 답변 로직 (사용자가 메시지를 보냈거나 카테고리를 클릭했을 때)
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        current_prompt = st.session_state.messages[-1]["content"]
        
        # 1990년 창립된 건설 IT 선도주자 KCIM HR 매니저 페르소나
        system_instruction = f"너는 1990년 창립된 KCIM의 전문 HR 매니저야. {user['name']}님에게 정중하게 답변해줘. [원칙] 시설/차량/숙소는 이경한 매니저 안내. 번호 02-772-5806."
        
        try:
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_instruction}] + st.session_state.messages)
            ans = completion.choices[0].message.content
            st.session_state.messages.append({"role": "assistant", "content": ans})
            st.rerun()
        except: pass
