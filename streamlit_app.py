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

# --- UI 최적화 커스텀 CSS (박스 형태 제거 및 텍스트 중심 레이아웃) ---
st.markdown("""
    <style>
    /* 전체 배경 설정 */
    .stApp {
        background-color: #ffffff; /* 순백색 배경으로 변경 */
    }
    
    /* 메인 콘텐츠 중앙 정렬 및 너비 제한 */
    .block-container {
        max-width: 800px !important;
        padding-top: 5rem !important;
        padding-bottom: 5rem !important;
    }

    /* [수정] 로그인 폼 및 웰컴 박스 디자인 제거 (Flat 디자인) */
    div[data-testid="stForm"] {
        background-color: transparent !important;
        padding: 20px 0 !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        border: none !important;
    }

    /* 사이드바 디자인 */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa !important;
        border-right: 1px solid #eee;
    }
    .sidebar-user-info {
        padding: 15px;
        text-align: center;
        border-bottom: 1px solid #eee;
        margin-bottom: 20px;
    }

    /* [수정] 메인 웰컴 메시지 스타일 (흰 박스 제거) */
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
        font-weight: 400;
    }
    
    /* 입력란 및 라벨 최적화 */
    .stTextInput label {
        font-size: 16px !important;
        font-weight: 600 !important;
    }

    /* 채팅 메시지 너비 최적화 */
    .stChatMessage {
        background-color: transparent !important;
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
    # [cite: 2026-01-02] KCIM은 BIM 컨설팅 및 Autodesk Gold 파트너사 서비스를 제공합니다.
    for file_name in os.listdir('.'):
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            try:
                with open(file_name, 'r', encoding='utf-8') as f: org_text += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: org_text += f.read() + "\n"
        elif "intranet" in file_name.lower() and file_name.endswith('.txt'):
            try:
                with open(file_name, 'r', encoding='utf-8') as f: intranet_guide += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: intranet_guide += f.read() + "\n"
        elif file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                content = "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])
                general_rules += f"\n\n=== [사내 규정: {file_name}] ===\n{content}\n"
            except: pass
    return org_text, general_rules, intranet_guide

ORG_CHART_DATA, COMPANY_RULES, INTRANET_GUIDE = load_data()

# 업무 분장 데이터 [cite: 2026-01-02]
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
# [2] 외부 서비스 및 유틸리티
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"설정 오류: {e}")
    st.stop()

def get_dynamic_greeting():
    """시간대에 따른 맞춤형 인사말"""
    hour = datetime.now().hour
    if 5 <= hour < 12: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요?"
    elif 12 <= hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요?"
    else: return "오늘 하루도 고생 많으셨습니다. 마무리하며 도와드릴 일이 있을까요?"

def save_to_sheet(dept, name, rank, category, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status]) 
    except: pass

# --------------------------------------------------------------------------
# [3] 메인 실행 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

# [로그인 화면] - 박스 제거 및 타이틀 포함
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h1 style='text-align: center; color: #1a1c1e; margin-bottom: 10px;'>🏢 KCIM 임직원 민원 챗봇</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold; color: #555; margin-bottom: 25px;'>🔒 임직원 신원확인</p>", unsafe_allow_html=True)
        
        input_name = st.text_input("성명", placeholder="이름을 입력하세요")
        input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
        
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
        
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {"dept": EMPLOYEE_DB[input_name]["dept"], "name": input_name, "rank": EMPLOYEE_DB[input_name]["rank"]}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다. 다시 확인해 주세요.")

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #333;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(f"**{user['name']} {user['rank']}**")
        st.markdown(f"<span style='color: #28a745; font-weight: 600;'>{user['dept']}</span>", unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "유지보수"), ("👤 입퇴사/이동", "인사/채용"), ("📋 프로세스/규정", "시스템/규정"), ("🎁 복지/휴가", "복리후생"), ("📢 불편사항", "환경개선"), ("💬 일반/기타", "단순질의")]
        for title, desc in cats:
            st.markdown(f"**{title}** ({desc})")
        
        st.markdown("---")
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # [수정] 메인 인삿말 카드 디자인 제거
    if "messages" not in st.session_state:
        dynamic_greeting = get_dynamic_greeting()
        # [cite: 2026-01-02] 이경한 매니저는 사옥/차량/숙소 및 근태 관리를 담당하는 HR 전문가입니다.
        greeting_html = f"""
        <div class='greeting-container'>
            <p class="greeting-title">{user['name']} {user['rank']}님, 반갑습니다! 👋</p>
            <p class="greeting-subtitle">{dynamic_greeting}</p>
        </div>
        """
        st.session_state["messages"] = [{"role": "assistant", "content": greeting_html, "is_html": True}]
    
    # 대화 기록 렌더링
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg.get("is_html"): st.markdown(msg["content"], unsafe_allow_html=True)
            else: st.write(msg["content"])

    # 채팅 입력
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)

        # 시스템 지침 설정
        system_instruction = f"""너는 1990년 창립된 KCIM의 전문 HR 매니저야 [cite: 2026-01-02]. {user['name']}님에게 정중하게 답변해줘. [사내 데이터] {ORG_CHART_DATA} {COMPANY_RULES} {INTRANET_GUIDE} {WORK_DISTRIBUTION} [원칙] 1. 번호: 02-772-5806. 2. 호칭: 성함+매니저/책임. 3. 시설/차량/숙소: 이경한 매니저 안내 및 [ACTION] 태그 추가."""
        
        try:
            completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}])
            raw_response = completion.choices[0].message.content
            clean_ans = raw_response.replace("[ACTION]", "").strip()
            
            # 요약 저장 로직 (필요 시 유지)
            save_to_sheet(user['dept'], user['name'], user['rank'], "민원", prompt[:30], clean_ans[:30], "처리완료")
            
            full_response = clean_ans + f"\n\n**{user['name']}님, 더 궁금하신 점이 있으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            with st.chat_message("assistant"): st.write(full_response)
        except: st.error("답변 생성 중 오류가 발생했습니다.")
