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
# [1] 직원 데이터베이스 로드 (새로 올린 파일 연동)
# 파일명: 구성원(정상)__20260115121840.xlsx - 구성원(정상).csv
# --------------------------------------------------------------------------
@st.cache_data
def load_employee_db():
    # 업로드해주신 파일명 (정확해야 합니다)
    file_name = '구성원(정상)__20260115121840.xlsx - 구성원(정상).csv'
    
    db = {}
    
    # 관리자 계정 (비상용)
    db["관리자"] = {"pw": "1234", "dept": "HR팀", "rank": "매니저"}

    if os.path.exists(file_name):
        try:
            # CSV 파일 읽기
            # 1. utf-8로 먼저 시도하고, 실패하면 cp949(한글 윈도우)로 시도
            try:
                df = pd.read_csv(file_name)
            except UnicodeDecodeError:
                df = pd.read_csv(file_name, encoding='cp949')
            
            # 데이터 정제 및 DB 구축
            # 새 파일 헤더: [이름, 부서, 직급, 휴대폰 번호]
            for _, row in df.iterrows():
                # 데이터가 비어있을 수 있으므로 문자열로 변환 후 공백 제거
                name = str(row['이름']).strip()
                dept = str(row['부서']).strip()
                rank = str(row['직급']).strip()
                phone = str(row['휴대폰 번호']).strip()
                
                # 휴대폰 번호에서 숫자만 추출 ('-' 제거)
                phone_digits = re.sub(r'[^0-9]', '', phone)
                
                # 뒷 4자리를 비밀번호로 사용
                if len(phone_digits) >= 4:
                    pw = phone_digits[-4:]
                else:
                    pw = "0000" # 번호가 없거나 짧으면 0000
                
                # DB에 저장
                db[name] = {
                    "pw": pw,
                    "dept": dept,
                    "rank": rank
                }
        except Exception as e:
            st.error(f"직원 명단 파일 로드 중 오류 발생: {e}")
            st.write("오류 상세:", e)
    else:
        st.warning(f"⚠️ '{file_name}' 파일을 찾을 수 없습니다. (GitHub에 업로드되었는지 확인해주세요)")
        
    return db

# DB 로드 실행
EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [2] 구글 시트 주소 (기존 주소 유지)
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
        
        # 시트 열기 (탭 이름: 응답시트)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        
        # 날짜 기록
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 순서: [날짜, 부서, 성명, 직급, 질문, 답변, 비고]
        sheet.append_row([now, dept, name, rank, question, answer, ""]) 
        
        print(f"✅ 기록 완료: {dept} {name} {rank}")
        
    except Exception as e:
        st.error(f"기록 실패: {e}")

# 4. 로그인 화면 (자동 인식 버전)
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
                st.warning("성명과 비밀번호를 모두 입력해주세요.")
                return

            # DB에서 확인
            if input_name in EMPLOYEE_DB:
                user_data = EMPLOYEE_DB[input_name]
                if user_data["pw"] == input_pw:
                    # 로그인 성공 -> 세션에 정보 저장
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
                    st.error("비밀번호(휴대폰 뒷 4자리)가 일치하지 않습니다.")
            else:
                st.error("등록되지 않은 직원입니다. (관리자에게 문의)")

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
            
            [사내 규정 요약]
            1. 법인차량: 그룹웨어 신청, 키는 3층 경영지원팀 수령.
            2. 연차: 팀장 전결(3일 이상 본부장), 반차 사용 가능.
            3. 경조사: 결혼(본인 50/5일), 1주일 전 신청서 제출.
            4. 기타: 규정에 없거나 시설 민원은 "담당자 확인 후 처리해 드리겠습니다."라고 답하고 끝에 [민원접수] 태그를 붙여.
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
