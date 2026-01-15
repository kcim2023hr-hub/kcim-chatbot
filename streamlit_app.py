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
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드
# --------------------------------------------------------------------------

# 1-1. 직원 명단 로드
@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    db["관리자"] = {"pw": "1234", "dept": "HR팀", "rank": "매니저"}

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
                except:
                    continue
        except Exception as e:
            st.error(f"❌ 엑셀 파일 읽기 실패: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

# 1-2. 데이터 로드 (조직도 vs 일반규정 분리)
@st.cache_data
def load_data():
    org_text = ""
    general_rules = ""
    
    for file_name in os.listdir('.'):
        # 1. 조직도 파일(org_chart.txt)
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            if file_name.endswith('.txt'):
                try:
                    with open(file_name, 'r', encoding='utf-8') as f:
                        org_text += f.read() + "\n"
                except:
                    with open(file_name, 'r', encoding='cp949') as f:
                        org_text += f.read() + "\n"
            continue 

        # 2. PDF 규정
        if file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                content = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted: content += extracted + "\n"
                general_rules += f"\n\n=== [사내 규정 파일: {file_name}] ===\n{content}\n"
            except: pass
        
        # 3. TXT 자료 (업무분장표 등)
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                with open(file_name, 'r', encoding='utf-8') as f: content = f.read()
            except:
                with open(file_name, 'r', encoding='cp949') as f: content = f.read()
            general_rules += f"\n\n=== [참고 자료: {file_name}] ===\n{content}\n"

    return org_text, general_rules

ORG_CHART_DATA, COMPANY_RULES = load_data()

# --------------------------------------------------------------------------
# [2] 구글 시트 및 OpenAI 설정
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

def save_to_sheet(dept, name, rank, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, dept, name, rank, question, answer, status]) 
    except Exception as e:
        pass

def check_finish_intent(user_input):
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "사용자가 '네, 없습니다', '종료', '끝' 등 대화를 끝내는 의도면 'FINISH', 질문이 이어지면 'CONTINUE'로 답해."},
                {"role": "user", "content": user_input}
            ],
            temperature=0
        )
        return completion.choices[0].message.content.strip()
    except:
        return "CONTINUE"

# --------------------------------------------------------------------------
# [3] 메인 로직
# --------------------------------------------------------------------------
def login():
    st.header("🔒 임직원 접속 (신원확인)")
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        input_name = col1.text_input("성명")
        input_pw = col2.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
        if st.form_submit_button("접속하기"):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {
                    "dept": EMPLOYEE_DB[input_name]["dept"],
                    "name": input_name,
                    "rank": EMPLOYEE_DB[input_name]["rank"]
                }
                st.rerun()
            else:
                st.error("정보가 일치하지 않습니다.")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
else:
    user = st.session_state["user_info"]
    
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user['rank']}**")
        st.markdown(f"🏢 **{user['dept']}**")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        
        # 관리자용 디버그 (이경한, 관리자만)
        if user['name'] in ["이경한", "관리자"]:
            st.divider()
            with st.expander("🛠️ 데이터 읽기 상태 확인"):
                st.write("✅ [1] 조직도 데이터 (앞부분)")
                st.text(ORG_CHART_DATA[:300])
                st.write("✅ [2] 규정/업무분장 데이터 (앞부분)")
                st.text(COMPANY_RULES[:300])

    st.markdown(f"### 👋 안녕하세요, {user['name']} {user['rank']}님!")
    st.markdown("무엇을 도와드릴까요?")

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "규정이나 결재 관련 궁금한 점이 있으신가요?"}]
    
    if "awaiting_confirmation" not in st.
