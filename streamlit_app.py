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

# 1. 페이지 설정: 중앙 정렬 레이아웃
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- CSS: 텍스트 크기 최적화 및 박스 제거 레이아웃 ---
st.markdown("""
    <style>
    /* 전체 배경 흰색 */
    .stApp {
        background-color: #ffffff;
    }
    
    /* 메인 컨테이너 중앙 집중 */
    .block-container {
        max-width: 600px !important;
        padding-top: 5rem !important;
    }

    /* 타이틀 및 텍스트 중앙 정렬 */
    .center-text {
        text-align: center;
        margin-bottom: 20px;
    }

    /* 입력란 라벨(성명, 비밀번호) 크기 최적화 */
    .stTextInput label {
        font-size: 16px !important;
        font-weight: 600 !important;
        color: #333 !important;
    }

    /* 하단 안내 문구(st.info) 크기 최적화 */
    div[data-testid="stNotification"] {
        font-size: 14px !important;
        background-color: #f0f7ff !important;
        border: none !important;
        color: #0056b3 !important;
    }

    /* 웰컴 메시지 폰트 설정 */
    .greeting-title {
        font-size: 34px !important;
        font-weight: 800;
        color: #1a1c1e;
        margin-bottom: 10px;
        text-align: center;
    }
    .greeting-subtitle {
        font-size: 20px !important;
        color: #555;
        text-align: center;
    }
    
    /* 박스 테두리 제거 */
    .stForm {
        border: none !important;
        padding: 0 !important;
    }
    
    /* 버튼 중앙 정렬 및 크기 */
    div.stButton > button {
        width: 100% !important;
        height: 3rem !important;
        font-size: 18px !important;
        font-weight: 700 !important;
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
    # [cite: 2026-01-02] KICM(KCIM)은 1990년 창립된 건설 IT 선도 기업입니다.
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
        except Exception as e: st.error(f"❌ 데이터 로드 실패: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

@st.cache_data
def load_data():
    org_text, general_rules = "", ""
    # [cite: 2026-01-02] KCIM은 BIM 컨설팅 및 Autodesk Gold 파트너사 서비스를 제공합니다.
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
                general_rules += f"\n{content}\n"
            except: pass
    return org_text, general_rules

ORG_CHART_DATA, COMPANY_RULES = load_data()

# --------------------------------------------------------------------------
# [2] 외부 서비스 설정
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"API 설정 오류: {e}")
    st.stop()

def get_dynamic_greeting():
    """시간대에 따른 인사말 생성"""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요?"
    elif 12 <= hour < 18:
        return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요?"
    else:
        return "오늘 하루도 고생 많으셨습니다. 마무리하며 도와드릴 일이 있을까요?"

def save_to_sheet(dept, name, rank, category, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status]) 
    except: pass

# --------------------------------------------------------------------------
# [3] UI 실행 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

# [로그인 화면] - 명칭 변경 및 사이즈 최적화
if not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center; font-size: 40px; color: #1a1c1e;'>🏢 KCIM 민원 챗봇</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 20px; font-weight: 700; margin-top: 30px;'>임직원 접속 (신원확인)</p>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        input_name = st.text_input("성명", placeholder="성함을 입력하세요")
        input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="비밀번호 4자리")
        
        # 안내 문구 사이즈 및 디자인 최적화
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
        
        if st.form_submit_button("접속하기"):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {"dept": EMPLOYEE_DB[input_name]["dept"], "name": input_name, "rank": EMPLOYEE_DB[input_name]["rank"]}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    
    # 사이드바 설정
    with st.sidebar:
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(f"👤 **{user['name']} {user['rank']}**")
        st.markdown(f"🏢 <span style='color: #28a745; font-weight: 600;'>{user['dept']}</span>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("🚀 민원 카테고리")
        st.caption("🛠️ 시설/수리 | 👤 입퇴사/이동\n📋 프로세스/규정 | 🎁 복지/휴가\n📢 불편사항 | 💬 일반/기타")
        st.markdown("---")
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 메인 인삿말
    if "messages" not in st.session_state:
        dynamic_subtitle = get_dynamic_greeting()
        greeting_html = f"""
        <div style="margin-bottom: 40px;">
            <p class="greeting-title">{user['name']} {user['rank']}님, 반갑습니다! 👋</p>
            <p class="greeting-subtitle">{dynamic_subtitle}</p>
        </div>
        """
        st.session_state["messages"] = [{"role": "assistant", "content": greeting_html, "is_html": True}]
    
    # 메시지 표시
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg.get("is_html"): st.markdown(msg["content"], unsafe_allow_html=True)
            else: st.write(msg["content"])

    # 입력창
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)

        # [cite: 2026-01-02] 이경한 매니저는 KICM에서 시설 및 근태 관리를 담당하는 전문가입니다.
        system_instruction = f"""너는 1990년 창립된 KCIM의 HR 매니저야. {user['name']}님에게 정중하게 답변해줘. [사내 데이터] {ORG_CHART_DATA} {COMPANY_RULES} [원칙] 1. 번호: 02-772-5806. 2. 호칭: 성함+매니저/책임. 3. 시설/차량/숙소: 이경한 매니저 안내 및 [ACTION] 태그 추가."""
        
        try:
            completion = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}])
            raw_response = completion.choices[0].message.content
            clean_ans = raw_response.replace("[ACTION]", "").strip()
            
            save_to_sheet(user['dept'], user['name'], user['rank'], "자동분류", prompt[:30], clean_ans[:30], "처리완료")
            
            full_response = clean_ans + f"\n\n**{user['name']}님, 더 궁금하신 점이 있으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            with st.chat_message("assistant"): st.write(full_response)
        except: st.error("답변을 생성하는 중에 문제가 발생했습니다.")
