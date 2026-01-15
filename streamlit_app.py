import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
import time
import os
import re

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 직원 데이터베이스 로드 (파일명: members.csv)
# --------------------------------------------------------------------------
@st.cache_data
def load_employee_db():
    # 이름을 단순하게 바꿨습니다.
    file_name = 'members.csv' 
    
    db = {}
    
    # 관리자 계정 (비상용)
    db["관리자"] = {"pw": "1234", "dept": "HR팀", "rank": "매니저"}

    if os.path.exists(file_name):
        try:
            # CSV 파일 읽기
            try:
                df = pd.read_csv(file_name)
            except UnicodeDecodeError:
                df = pd.read_csv(file_name, encoding='cp949')
            
            # 데이터 정제
            for _, row in df.iterrows():
                name = str(row['이름']).strip()
                dept = str(row['부서']).strip()
                rank = str(row['직급']).strip()
                phone = str(row['휴대폰 번호']).strip()
                
                # 휴대폰 번호 숫자만 추출
                phone_digits = re.sub(r'[^0-9]', '', phone)
                
                # 뒷 4자리 비밀번호
                if len(phone_digits) >= 4:
                    pw = phone_digits[-4:]
                else:
                    pw = "0000"
                
                db[name] = {
                    "pw": pw,
                    "dept": dept,
                    "rank": rank
                }
        except Exception as e:
            st.error(f"❌ 파일 읽기 오류: {e}")
    else:
        # 파일이 없을 때, 현재 폴더에 무슨 파일이 있는지 보여주는 진단 기능
        st.error(f"⚠️ '{file_name}' 파일을 찾을 수 없습니다.")
        st.warning(f"📂 현재 폴더에 있는 파일 목록: {os.listdir('.')}")
        st.info("GitHub에 'members.csv'라는 이름으로 파일을 업로드했는지 확인해주세요.")
        
    return db

# DB 로드 실행
EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [2] 구글 시트 주소
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603"

# 2. 비밀번호(Secrets) 불러오기
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

# 3. 구글 시트 연결 및 저장 함수
def save_to_sheet(dept, name, rank, question, answer):
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, dept, name, rank, question, answer, ""]) 
        
    except Exception as e:
        st.error(f"기록 실패: {e}")

# 4. 로그인 화면
def login():
    st.header("🔒 임직원 접속 (신원확인)")
    st.caption("성명과 휴대폰 번호 뒷 4자리를 입력해주세요.")
    
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        input_name = col1.text_input("성명", placeholder="예: 홍길동")
        input_pw = col2.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="예: 1234")
        
        submit_button = st.form_submit_button("접속하기")
        
        if submit_button:
            if not input_name or not input_pw:
                st.warning("정보를 모두 입력해주세요.")
                return

            if input_name in EMPLOYEE_DB:
                user_data = EMPLOYEE_DB[input_name]
                if user_data["pw"] == input_pw:
                    st.session_state["logged_in"] = True
                    st.session_state["user_info"] = {
                        "dept": user_data["dept"],
                        "name": input_name,
                        "rank": user_data["rank"]
                    }
                    st.success(f"{input_name} {user_data['rank']}님, 환영합니다!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("비밀번호가 일치하지 않습니다.")
            else:
                st.error("명단에 없는 이름입니다.")

# 5. 메인 로직
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
else:
    user = st.session_state["user_info"]
    st.markdown(f"👤 **{user['dept']} | {user['name']} {user['rank']}**님 접속 중")
    
    if st.button("로그아웃"):
        st.session_state["logged_in"] = False
        st.rerun()
    st.markdown("---")

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "반갑습니다. KCIM HR 규정 및 민원 챗봇입니다."}]

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        response = ""
        try:
            system_instruction = """
            너는 KCIM(케이씨아이엠)의 HR/총무 담당 AI 매니저야.
            임직원의 질문에 대해 아래 [사내 규정]을 기반으로 친절하고 명확하게 답변해.
            """
            
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ]
            )
            response = completion.choices[0].message.content
        except Exception as e:
            response = f"오류 발생: {e}"

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.chat_message("assistant").write(response)
        
        save_to_sheet(user['dept'], user['name'], user['rank'], prompt, response)
