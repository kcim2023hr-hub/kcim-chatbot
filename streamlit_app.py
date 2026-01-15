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
    # 관리자용 슈퍼 계정
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
        
        # 순서: [날짜, 부서, 성명, 직급, 질문, 답변, 처리결과]
        sheet.append_row([now, dept, name, rank, question, answer, status]) 
        
    except Exception as e:
        st.error(f"구글 시트 기록 실패: {e}")

# 사용자 의도 파악 (종료 vs 계속)
def check_finish_intent(user_input):
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "사용자가 '네, 없습니다', '종료', '끝' 등의 의미로 말하면 'FINISH', '아니요', '질문 더 있어요' 등의 의미면 'CONTINUE'라고 답해."},
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

# 세션 초기화
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
    
    # 상태 관리: 답변 후 종료 확인 대기 중인가?
    if "awaiting_confirmation" not in st.session_state:
        st.session_state["awaiting_confirmation"] = False
    
    # 마지막 대화 내용 임시 저장소
    if "temp_log" not in st.session_state:
        st.session_state["temp_log"] = {"q": "", "a": "", "status": ""}

    # 화면에 대화 기록 뿌리기
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    # 사용자 입력 처리
    if prompt := st.chat_input("내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # [CASE 1] "더 민원이 없으십니까?"에 대한 답변인 경우
        if st.session_state["awaiting_confirmation"]:
            intent = check_finish_intent(prompt)
            
            # 이전 대화 내용 가져오기
            last_q = st.session_state["temp_log"]["q"]
            last_a = st.session_state["temp_log"]["a"]
            last_status = st.session_state["temp_log"]["status"]

            if intent == "FINISH":
                # 사용자가 "없습니다(종료)" 선택 -> 시트에 저장하고 종료
                save_to_sheet(user['dept'], user['name'], user['rank'], last_q, last_a, last_status)
                
                end_msg = "감사합니다. 상담 내용이 기록되었습니다. 챗봇을 종료하거나 새로운 질문을 입력해주세요."
                st.session_state.messages.append({"role": "assistant", "content": end_msg})
                st.chat_message("assistant").write(end_msg)
                
                # 상태 초기화
                st.session_state["awaiting_confirmation"] = False
                st.session_state["temp_log"] = {}
                
            else:
                # 사용자가 "아니요, 더 있어요" 선택 -> 이전 건은 일단 저장하고 계속 진행
                save_to_sheet(user['dept'], user['name'], user['rank'], last_q, last_a, last_status)
                
                # 이번 입력이 '질문'일 수도 있으므로 바로 답변 생성 로직으로 넘기기 위해
                # 단순 플래그 해제만 하고 아래 [CASE 2] 로직을 타게 하거나,
                # 여기서는 "네, 어떤 점이 더 궁금하신가요?"라고 묻고 끝낼 수도 있습니다.
                # (매니저님 요청: 바로 질문에 답하는게 자연스러우므로 아래 로직을 호출하거나 재실행 필요)
                # 여기서는 간단히 '새로운 질문'으로 간주하고 바로 답변 생성으로 넘어가겠습니다.
                st.session_state["awaiting_confirmation"] = False
                # (아래 코드가 이어지면서 처리됨)

        # [CASE 2] 일반 질문 처리 (확인 대기 상태가 아니거나, "더 있어요"라고 한 뒤)
        if not st.session_state["awaiting_confirmation"]:
            # AI 시스템 프롬프트 (가장 중요한 부분!)
            system_instruction = """
            너는 KCIM의 HR/총무 AI 매니저야.
            임직원 질문에 대해 규정에 따라 답변하되, 질문의 성격에 따라 답변 맨 앞에 태그를 붙여야 해.
            
            [태그 규칙]
            1. [ACTION]: 시설 고장, 수리 요청, 현장 확인이 필요한 민원, 혹은 네가 해결 불가능한 문제.
               - 답변 예시: "[ACTION] 접수되었습니다. 시설 담당자가 현장을 확인하고 조치하겠습니다."
            2. [INFO]: 단순 규정 문의, 절차 안내, 정보 제공 등 AI가 답변으로 해결 가능한 경우.
               - 답변 예시: "[INFO] 법인차량은 그룹웨어에서 신청 가능하며, 키는 3층에서 수령합니다."
            
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
                raw_response = "[INFO] 오류가 발생했습니다."

            # 태그 분석 및 처리결과 결정
            if "[ACTION]" in raw_response:
                final_status = "담당자확인필요"
                clean_response = raw_response.replace("[ACTION]", "").strip()
            else:
                final_status = "처리완료"
                clean_response = raw_response.replace("[INFO]", "").strip()

            # 답변 출력 (태그 뗀 버전)
            full_response = clean_response + "\n\n**더 이상의 민원은 없으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.chat_message("assistant").write(full_response)

            # 임시 저장 (사용자가 "없습니다" 할 때까지 대기)
            st.session_state["temp_log"] = {
                "q": prompt,
                "a": clean_response,
                "status": final_status
            }
            st.session_state["awaiting_confirmation"] = True
