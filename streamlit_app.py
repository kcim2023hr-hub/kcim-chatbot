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

# --- UI 최적화 커스텀 CSS (메인 플랫 유지 + 사이드바 개별 박스 처리) ---
st.markdown("""
    <style>
    /* 전체 배경 설정 */
    .stApp {
        background-color: #ffffff;
    }
    
    /* 메인 콘텐츠 중앙 정렬 및 너비 제한 */
    .block-container {
        max-width: 800px !important;
        padding-top: 5rem !important;
        padding-bottom: 5rem !important;
    }

    /* 사이드바 배경색 설정 */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa !important;
    }

    /* [요청사항] 사이드바 개별 박스 스타일 (Card 스타일) */
    .sidebar-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
        margin-bottom: 12px;
    }
    
    .sidebar-user-name {
        font-size: 18px;
        font-weight: 700;
        color: #1a1c1e;
        display: block;
        margin-bottom: 4px;
    }
    
    .sidebar-dept-tag {
        font-size: 14px;
        font-weight: 600;
        color: #28a745;
    }

    /* 메인 웰컴 메시지 스타일 (플랫 디자인 유지) */
    .greeting-container {
        text-align: center;
        margin-bottom: 40px;
        padding: 20px 0;
    }
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
    
    /* 입력란 및 버튼 스타일 최적화 */
    .stTextInput label {
        font-size: 16px !important;
        font-weight: 600 !important;
    }
    div[data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
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
    # [cite: 2026-01-02] KICM(KCIM)은 1990년 창립된 건설 IT 분야의 선도주자입니다.
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
        except Exception as e: st.error(f"❌ 데이터 로드 오류: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

@st.cache_data
def load_data():
    org_text, general_rules, intranet_guide = "", "", ""
    for file_name in os.listdir('.'):
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            try:
                with open(file_name, 'r', encoding='utf-8') as f: org_text += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: org_text += f.read() + "\n"
        elif file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                content = "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])
                general_rules += f"\n\n=== [사내 규정: {file_name}] ===\n{content}\n"
            except: pass
    return org_text, general_rules

ORG_CHART_DATA, COMPANY_RULES = load_data()

# --------------------------------------------------------------------------
# [2] 외부 서비스 및 유틸리티
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"환경 설정 오류: {e}")
    st.stop()

def get_dynamic_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요?"
    elif 12 <= hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요?"
    else: return "오늘 하루도 고생 많으셨습니다. 마무리하며 도와드릴 일이 있을까요?"

# --------------------------------------------------------------------------
# [3] UI 실행 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

# [로그인 화면] - 플랫 타이틀 구성
if not st.session_state["logged_in"]:
    st.markdown("<div class='greeting-container'><h1 class='greeting-title'>🏢 KCIM 임직원 민원 챗봇</h1></div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<p style='text-align: center; font-weight: bold; margin-bottom: 20px;'>🔒 임직원 신원확인</p>", unsafe_allow_html=True)
            input_name = st.text_input("성명", placeholder="이름을 입력하세요")
            input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
            st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
            if st.form_submit_button("접속하기", use_container_width=True):
                if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                    st.session_state["logged_in"] = True
                    st.session_state["user_info"] = {"dept": EMPLOYEE_DB[input_name]["dept"], "name": input_name, "rank": EMPLOYEE_DB[input_name]["rank"]}
                    st.rerun()
                else: st.error("정보가 일치하지 않습니다.")

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    
    # --- 좌측 사이드바: 각 섹션을 개별 '박스'로 처리 ---
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; margin-bottom: 20px;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        
        # 1. 접속 정보 박스
        st.markdown(f"""
        <div class="sidebar-card">
            <small style="color: #6c757d;">인증된 사용자</small>
            <span class="sidebar-user-name">{user['name']} {user['rank']}</span>
            <span class="sidebar-dept-tag">{user['dept']}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 2. 민원 카테고리 박스 (그룹화)
        st.markdown("<p style='font-size: 14px; font-weight: 700; margin-left: 5px; margin-bottom: 8px;'>🚀 민원 카테고리</p>", unsafe_allow_html=True)
        cats = [
            ("🛠️ 시설/수리", "유지보수"), ("👤 입퇴사/이동", "인사/채용"),
            ("📋 프로세스/규정", "시스템/규정"), ("🎁 복지/휴가", "복리후생"),
            ("📢 불편사항", "환경개선"), ("💬 일반/기타", "단순질의")
        ]
        
        for title, desc in cats:
            st.markdown(f"""
            <div class="sidebar-card" style="padding: 10px 15px; margin-bottom: 8px;">
                <span style="font-size: 14px; font-weight: 600;">{title}</span>
                <span style="font-size: 12px; color: #888; display: block;">{desc}</span>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # --- 메인 채팅창: 플랫 디자인 유지 ---
    if "messages" not in st.session_state:
        dynamic_greeting = get_dynamic_greeting()
        # [cite: 2026-01-02] 이경한 매니저는 KICM HR팀 소속으로 시설, 차량, 근태 관리를 담당합니다.
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

        # 시스템 페르소나 적용 [cite: 2026-01-02]
        system_instruction = f"""너는 1990년 창립된 KCIM의 전문 HR 매니저야. {user['name']}님에게 정중하게 답변해줘. [사내 데이터] {ORG_CHART_DATA} {COMPANY_RULES} [원칙] 1. 번호: 02-772-5806. 2. 호칭: 성함+매니저/책임. 3. 시설/차량/숙소: 이경한 매니저 안내 및 [ACTION] 태그 추가."""
        
        try:
            completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}])
            raw_response = completion.choices[0].message.content
            clean_ans = raw_response.replace("[ACTION]", "").strip()
            
            full_response = clean_ans + f"\n\n**{user['name']}님, 더 궁금하신 점이 있으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            with st.chat_message("assistant"): st.write(full_response)
        except: st.error("답변 생성 오류가 발생했습니다.")
