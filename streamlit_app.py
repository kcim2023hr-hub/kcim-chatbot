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
# [1] 직원 데이터베이스 로드 (파일명: members.xlsx)
# --------------------------------------------------------------------------
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
                    if len(phone_digits) >= 4:
                        pw = phone_digits[-4:]
                    else:
                        pw = "0000"
                    
                    db[name] = {"pw": pw, "dept": dept, "rank": rank}
                except:
                    continue
        except Exception as e:
            st.error(f"❌ 엑셀 파일 읽기 실패: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

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

# 구글 시트 저장 함수
def save_to_sheet(dept, name, rank, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        sheet.append_row([now, dept, name, rank, question, answer, status]) 
        
    except Exception as e:
        st.error(f"구글 시트 기록 실패: {e}")

# 종료 의도 파악
def check_finish_intent(user_input):
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "사용자가 '네, 없습니다', '종료', '끝', '수고하세요' 등 대화를 끝내는 말이거나, 단순한 인사면 'FINISH'. 질문이 이어지면 'CONTINUE'로 답해."},
                {"role": "user", "content": user_input}
            ],
            temperature=0
        )
        return completion.choices[0].message.content.strip()
    except:
        return "CONTINUE"

# --------------------------------------------------------------------------
# [3] 로그인 및 메인 로직
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
    st.markdown(f"👤 **{user['dept']} | {user['name']} {user['rank']}**님")
    
    if st.button("로그아웃"):
        st.session_state.clear()
        st.rerun()
    st.divider()

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "반갑습니다. KCIM HR/총무 민원 챗봇입니다. 무엇을 도와드릴까요?"}]
    
    # 상태 관리
    if "awaiting_confirmation" not in st.session_state:
        st.session_state["awaiting_confirmation"] = False

    # 화면 표시
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    # 입력 처리
    if prompt := st.chat_input("내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # [CASE 1] "더 민원 없으신가요?"에 대한 대답 처리
        if st.session_state["awaiting_confirmation"]:
            intent = check_finish_intent(prompt)
            
            if intent == "FINISH":
                # [수정됨] 요청하신 따뜻한 멘트로 변경!
                end_msg = "늘 좋은 하루 보내세요😊"
                st.session_state.messages.append({"role": "assistant", "content": end_msg})
                st.chat_message("assistant").write(end_msg)
                
                st.session_state["awaiting_confirmation"] = False
                st.stop() 
            else:
                # 계속 질문 시 상태 해제
                st.session_state["awaiting_confirmation"] = False

        # [CASE 2] 질문 처리 및 즉시 저장
        if not st.session_state["awaiting_confirmation"]:
            # AI 답변 생성
            system_instruction = """
            너는 KCIM의 HR/총무 AI 매니저야.
            임직원 질문에 대해 규정에 따라 답변하되, 질문의 성격에 따라 답변 맨 앞에 태그를 붙여야 해.
            
            [태그 규칙]
            1. [ACTION]: 시설 고장, 수리 요청, 청소, 비품 파손 등 현장 확인이나 물리적 조치가 필요한 경우.
            2. [INFO]: 단순 규정 문의, 절차 안내, 정보 제공 등 AI가 텍스트로 해결 가능한 경우.
            
            [사내 규정 데이터]
            1. 법인차량: 그룹웨어 신청, 본사 3층 경영지원팀 키 수령, 운행일지 필수.
            2. 연차: 팀장 전결 (3일 이상은 본부장).
            3. 경조사: 결혼(본인 50만/5일), 1주일 전 신청.
            4. 숙소/시설: 민원 접수 시 담당자가 직접 확인 후 처리.
            """
            
            try:
                completion = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                )
                raw_response = completion.choices[0].message.content
            except Exception as e:
                raw_response = "[INFO] 시스템 오류가 발생했습니다."

            # 태그 처리
            if "[ACTION]" in raw_response:
                final_status = "담당자확인필요"
                clean_response = raw_response.replace("[ACTION]", "").strip()
            else:
                final_status = "처리완료"
                clean_response = raw_response.replace("[INFO]", "").strip()

            # 즉시 저장 (창 닫아도 안전)
            save_to_sheet(user['dept'], user['name'], user['rank'], prompt, clean_response, final_status)

            # 답변 출력
            full_response = clean_response + "\n\n**더 이상의 민원은 없으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.chat_message("assistant").write(full_response)

            # 종료 확인 대기
            st.session_state["awaiting_confirmation"] = True
