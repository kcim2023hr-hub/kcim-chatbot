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

# --- UI 고정 CSS: 중앙 플랫 디자인 + 사이드바 개별 박스 ---
st.markdown("""
    <style>
    /* 전체 배경 */
    .stApp {
        background-color: #ffffff;
    }
    
    /* 메인 컨테이너 중앙 정렬 및 너비 */
    .block-container {
        max-width: 800px !important;
        padding-top: 5rem !important;
    }

    /* [고정] 메인 화면 박스 형식 완전 제거 (Flat) */
    div[data-testid="stForm"], .greeting-container {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        text-align: center;
    }

    /* [고정] 좌측 사이드바만 개별 박스 처리 */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa !important;
    }
    .sidebar-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
        margin-bottom: 12px;
        text-align: center;
    }
    .sidebar-dept-tag {
        font-size: 14px;
        font-weight: 600;
        color: #28a745;
    }

    /* 텍스트 스타일링 */
    .greeting-title {
        font-size: 36px !important;
        font-weight: 800;
        color: #1a1c1e;
        margin-bottom: 15px;
    }
    .greeting-subtitle {
        font-size: 22px !important;
        color: #555;
    }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 데이터 로드 로직
# --------------------------------------------------------------------------

@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    db["관리자"] = {"pw": "1323", "dept": "HR팀", "rank": "매니저"}
    if os.path.exists(file_name):
        try:
            df = pd.read_excel(file_name, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            for _, row in df.iterrows():
                try:
                    name = str(row['이름']).strip()
                    dept = str(row['부서']).strip()
                    rank = str(row['직급']).strip()
                    phone = str(row['휴대폰 번호']).strip()
                    phone_digits = re.sub(r'[^0-9]', '', phone)
                    pw = phone_digits[-4:] if len(phone_digits) >= 4 else "0000"
                    db[name] = {"pw": pw, "dept": dept, "rank": rank}
                except: continue
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except Exception as e: st.error(f"❌ 데이터 로드 오류")
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [2] 외부 서비스 및 유틸리티
# --------------------------------------------------------------------------
def get_dynamic_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요?"
    elif 12 <= hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요?"
    else: return "오늘 하루도 고생 많으셨습니다. 마무리하며 도와드릴 일이 있을까요?"

# --------------------------------------------------------------------------
# [3] UI 실행
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

# [로그인 화면]
if not st.session_state["logged_in"]:
    st.markdown("<div class='greeting-container'><h1 class='greeting-title'>🏢 KCIM 임직원 민원 챗봇</h1></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<p style='text-align: center; font-weight: bold;'>🔒 임직원 신원확인</p>", unsafe_allow_html=True)
            input_name = st.text_input("성명", placeholder="이름 입력")
            input_pw = st.text_input("비밀번호", type="password", placeholder="****")
            st.info("💡 민원 데이터 관리를 위해 신원 확인을 진행합니다.")
            if st.form_submit_button("접속하기", use_container_width=True):
                if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                    st.session_state["logged_in"] = True
                    st.session_state["user_info"] = {"dept": EMPLOYEE_DB[input_name]["dept"], "name": input_name, "rank": EMPLOYEE_DB[input_name]["rank"]}
                    st.rerun()

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        # 접속 정보 박스
        st.markdown(f"""
        <div class="sidebar-card">
            <small>인증된 사용자</small><br>
            <b style="font-size: 18px;">{user['name']} {user['rank']}</b><br>
            <span class="sidebar-dept-tag">{user['dept']}</span>
        </div>
        """, unsafe_allow_html=True)
        # 카테고리 박스
        st.markdown("<p style='font-size: 14px; font-weight: 700; margin-left: 5px;'>🚀 민원 카테고리</p>", unsafe_allow_html=True)
        cats = [("🛠️ 시설/수리", "유지보수"), ("👤 입퇴사/이동", "인사/채용"), ("📋 프로세스/규정", "시스템/규정"), ("🎁 복지/휴가", "복리후생"), ("📢 불편사항", "환경개선"), ("💬 일반/기타", "단순질의")]
        for title, desc in cats:
            st.markdown(f"<div class='sidebar-card'><b>{title}</b><br><small>{desc}</small></div>", unsafe_allow_html=True)
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 메인 인삿말 (박스 없이 플랫하게 고정)
    if "messages" not in st.session_state:
        greeting_html = f"""
        <div class='greeting-container'>
            <p class="greeting-title">{user['name']} {user['rank']}님, 반갑습니다! 👋</p>
            <p class="greeting-subtitle">{get_dynamic_greeting()}</p>
        </div>
        """
        st.session_state["messages"] = [{"role": "assistant", "content": greeting_html, "is_html": True}]
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg.get("is_html"): st.markdown(msg["content"], unsafe_allow_html=True)
            else: st.write(msg["content"])

    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        # 답변 로직 생략 (기존과 동일)
