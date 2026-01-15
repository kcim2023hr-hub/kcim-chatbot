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

# 1. 페이지 설정: 중앙 정렬 레이아웃 고정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 및 카테고리 버튼 가독성 극대화 커스텀 CSS ---
st.markdown("""
    <style>
    /* 전체 배경 및 레이아웃 */
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }

    /* [로그인 화면] 폼 카드 스타일링 */
    div[data-testid="stForm"] {
        background-color: #ffffff !important;
        padding: 50px !important;
        border-radius: 20px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05) !important;
        border: 1px solid #e1e4e8 !important;
        text-align: center;
    }

    /* 파란색 안내 박스(st.info) 가독성 최적화 */
    div[data-testid="stNotification"] {
        font-size: 17px !important;
        font-weight: 500 !important;
        line-height: 1.6 !important;
        background-color: #f0f7ff !important;
        border-radius: 12px !important;
        color: #0056b3 !important;
        padding: 20px !important;
    }

    /* 입력란 라벨 폰트 크기 확대 */
    .stTextInput label {
        font-size: 18px !important;
        font-weight: 600 !important;
        color: #333 !important;
        margin-bottom: 10px !important;
        display: block;
        text-align: left !important;
    }

    /* [사이드바] 버튼 스타일링 (카드 박스 형태 고정) */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    
    .sidebar-user-box {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #edf0f2;
        margin-bottom: 20px;
        text-align: center;
    }

    /* [중요] 카테고리 버튼 내 제목과 내용의 시각적 구분 (CSS Trick) */
    div[data-testid="stSidebar"] .stButton > button {
        background-color: #ffffff !important;
        border: 1px solid #e9ecef !important;
        padding: 18px 15px !important;
        border-radius: 15px !important;
        width: 100% !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03) !important;
        margin-bottom: -5px !important;
        transition: all 0.2s ease !important;
    }

    /* 버튼 텍스트 전체 스타일 (기본적으로 내용 스타일로 설정) */
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p {
        font-size: 13px !important;
        color: #666 !important;
        line-height: 1.5 !important;
        white-space: pre-line !important; /* 줄바꿈 허용 */
        text-align: left !important;
        margin: 0 !important;
    }

    /* 버튼 첫 번째 줄(제목) 스타일 강제 변경 */
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p::first-line {
        font-size: 16px !important;
        font-weight: 700 !important;
        color: #1a1c1e !important;
    }

    div[data-testid="stSidebar"] .stButton > button:hover {
        border-color: #28a745 !important;
        background-color: #f8fff9 !important;
    }

    /* [메인화면] 플랫 디자인 인사말 */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 23px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 데이터 로드 로직 (1990년 창립 KCIM 정보 반영)
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

# 업무 분장 데이터 (HR팀 매니저 이경한 업무 중심)
WORK_DISTRIBUTION = """
- 이경한 매니저: 사옥/법인차량 관리, 현장 숙소 관리, 근태 관리, 행사 기획/실행, 임직원 제도 수립
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
# [3] 메인 실행 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []

# [로그인 화면]
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center; color: #1a1c1e; margin-bottom: 10px;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold; color: #555; margin-bottom: 30px;'>🔒 임직원 신원확인</p>", unsafe_allow_html=True)
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

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='sidebar-user-box'>
            <small style='color: #6c757d;'>인증된 사용자</small><br>
            <b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br>
            <span style='color: #28a745; font-weight: 600;'>{user['dept']}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        
        # 카테고리 리스트 (이미지 image_881631.png 상세 내용 반영)
        cats = [
            ("🛠️ 시설/수리", "사옥·차량 유지보수, 장비 교체 및 수리 요청"),
            ("👤 입퇴사/이동", "제증명 발급, 인사 발령, 근무 확인 및 채용"),
            ("📋 프로세스/규정", "사내 규정 안내, 시스템 이슈 및 보안 문의"),
            ("🎁 복지/휴가", "경조사, 지원금, 교육 지원 및 동호회 활동"),
            ("📢 불편사항", "근무 환경 내 불편 및 피해 사항 컴플레인"),
            ("💬 일반/기타", "단순 질의, 일반 업무 협조 및 기타 문의")
        ]
        
        for title, desc in cats:
            # 버튼 클릭 시 해당 카테고리로 대화 시작
            # \n을 사용하여 제목과 설명을 구분하며, CSS가 이를 감지해 스타일을 다르게 입힙니다.
            if st.button(f"{title}\n{desc}", key=title):
                st.session_state.messages.append({"role": "user", "content": f"[{title}] 카테고리에 대해 문의하고 싶습니다."})
        
        st.markdown("---")
        if st.button("🚪 안전하게 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 메인 인삿말 (최초 접속 시에만 표시되는 플랫 디자인)
    if not st.session_state.messages:
        greeting_html = f"""
        <div class='greeting-container'>
            <p class="greeting-title">{user['name']} {user['rank']}님, 반갑습니다! 👋</p>
            <p class="greeting-subtitle">{get_dynamic_greeting()}</p>
        </div>
        """
        st.markdown(greeting_html, unsafe_allow_html=True)
    
    # 대화 기록 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 채팅 입력
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()

    # 답변 생성 로직 (1990년 창립 KCIM 전문 HR 매니저 페르소나)
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        # Autodesk Gold 파트너사 정보 및 담당자 정보 반영
        system_instruction = f"너는 1990년 창립된 KCIM의 전문 HR 매니저야. {user['name']}님에게 정중히 답변해줘. 시설/차량/숙소는 이경한 매니저 안내(02-772-5806)."
        try:
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_instruction}] + st.session_state.messages)
            st.session_state.messages.append({"role": "assistant", "content": completion.choices[0].message.content})
            st.rerun()
        except: pass
