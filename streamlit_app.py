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

# --- UI 고정 및 가독성 최적화 커스텀 CSS ---
st.markdown("""
    <style>
    /* 전체 배경 */
    .stApp {
        background-color: #f4f7f9;
    }
    
    /* 중앙 집중형 레이아웃 */
    .block-container {
        max-width: 750px !important;
        padding-top: 5rem !important;
        padding-bottom: 5rem !important;
    }

    /* [로그인 화면] 폼 카드 스타일링 및 파란 박스 가독성 강화 */
    div[data-testid="stForm"] {
        background-color: #ffffff !important;
        padding: 45px !important;
        border-radius: 20px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05) !important;
        border: 1px solid #e1e4e8 !important;
        text-align: center;
    }

    /* 파란색 안내 박스(st.info) 가독성 최적화 */
    div[data-testid="stNotification"] {
        font-size: 16px !important; /* 글자 크기 확대 */
        font-weight: 500 !important;
        line-height: 1.6 !important;
        background-color: #f0f7ff !important;
        border: none !important;
        padding: 15px !important;
        border-radius: 10px !important;
        color: #0056b3 !important;
    }

    /* 입력란 라벨 및 폰트 크기 조절 */
    .stTextInput label {
        font-size: 17px !important;
        font-weight: 600 !important;
        color: #333 !important;
        text-align: left !important;
        display: block;
    }

    /* [사이드바] 개별 박스 스타일 고정 */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #dee2e6;
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
        font-size: 15px;
        font-weight: 600;
        color: #28a745;
    }

    /* [메인화면] 플랫 디자인 (박스 제거) 고정 */
    .greeting-container {
        text-align: center;
        margin-bottom: 40px;
        padding: 20px 0;
        background-color: transparent !important;
    }
    .greeting-title {
        font-size: 34px !important;
        font-weight: 800;
        color: #1a1c1e;
        margin-bottom: 15px;
    }
    .greeting-subtitle {
        font-size: 21px !important;
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
    # KCIM(KICM)은 1990년 창립된 건설 IT 분야 선도 기업입니다.
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
        except Exception: st.error("❌ 엑셀 파일 로드 실패")
    return db

EMPLOYEE_DB = load_employee_db()

# 업무 분장표 데이터 (HR팀 이경한 매니저 노하우 반영)
WORK_DISTRIBUTION = """
[경영관리본부 업무 분장표]
- 이경한 매니저: 사옥/법인차량 관리, 현장 숙소 관리, 근태 관리, 행사 기획/실행, 임직원 제도 수립
- 김병찬 매니저: 제도 공지, 위임전결, 취업규칙, 평가보상
- 백다영 매니저: 교육, 채용, 입퇴사 안내
- 김승민 책임: 품의서 관리, 세금계산서, 법인카드 비용처리, 숙소 비용 집행
- 안하련 매니저: 급여 서류(원천징수), 품의 금액 송금
- 손경숙 매니저: 비품 구매
- 최관식 매니저: 내부 직원 정보 관리 (어울지기, 플로우)
"""

# --------------------------------------------------------------------------
# [2] 유틸리티 기능
# --------------------------------------------------------------------------

def get_dynamic_greeting():
    """접속 시간에 따른 맞춤 인사말"""
    hour = datetime.now().hour
    if 5 <= hour < 12: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 12 <= hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    else: return "오늘 하루도 고생 많으셨습니다. 마무리하며 도와드릴 일이 있을까요? ✨"

# --------------------------------------------------------------------------
# [3] 메인 실행 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

# [로그인 화면] - 흰 박스 내부 타이틀 및 가독성 최적화
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        # 박스 내부 최상단 타이틀 고정
        st.markdown("<h2 style='text-align: center; color: #1a1c1e; margin-bottom: 10px;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold; color: #555; margin-bottom: 30px;'>🔒 임직원 신원확인</p>", unsafe_allow_html=True)
        
        input_name = st.text_input("성명", placeholder="이름을 입력하세요")
        input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
        
        # 가독성을 높인 파란색 안내 박스
        st.info("💡 민원 데이터 관리를 위해 해당 임직원의 신원 확인을 요청드립니다.")
        
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {"dept": EMPLOYEE_DB[input_name]["dept"], "name": input_name, "rank": EMPLOYEE_DB[input_name]["rank"]}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다. 다시 확인해 주세요.")

# [챗봇 메인 화면] - 사이드바 박스 & 메인 플랫 디자인 유지
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown("---")
        # 사용자 정보 (박스형)
        st.markdown(f"""
        <div class='sidebar-card'>
            <small style='color: #6c757d;'>인증된 사용자</small><br>
            <b style='font-size: 19px;'>{user['name']} {user['rank']}</b><br>
            <span class='sidebar-dept-tag'>{user['dept']}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "유지보수"), ("👤 입퇴사/이동", "인사/채용"), ("📋 프로세스/규정", "시스템/규정"), ("🎁 복지/휴가", "복리후생"), ("📢 불편사항", "환경개선"), ("💬 일반/기타", "단순질의")]
        for title, desc in cats:
            st.markdown(f"<div class='sidebar-card' style='padding: 10px;'><b>{title}</b><br><small>{desc}</small></div>", unsafe_allow_html=True)
        
        if st.button("🚪 안전하게 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 메인 인삿말 (플랫 디자인 고정)
    if "messages" not in st.session_state:
        dynamic_greeting = get_dynamic_greeting()
        greeting_html = f"""
        <div class='greeting-container'>
            <p class="greeting-title">{user['name']} {user['rank']}님, 반갑습니다! 👋</p>
            <p class="greeting-subtitle">{dynamic_greeting}</p>
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

        # 시스템 페르소나 적용
        system_instruction = f"너는 1990년 창립된 KCIM의 전문 HR 매니저야. {user['name']}님에게 정중하게 답변해줘. [사내 데이터] {WORK_DISTRIBUTION} [원칙] 1. 번호: 02-772-5806. 2. 호칭: 성함+매니저/책임. 3. 시설/차량/숙소: 이경한 매니저 안내 및 [ACTION] 태그 추가."
        
        # OpenAI 통신 및 답변 로직 (보안상 생략/기존 유지)
        # st.chat_message("assistant").write("...답변 생성 중...")
