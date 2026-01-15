import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import traceback
import time

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 직원 명단 (실제 사용 시 이 부분을 수정하세요)
# --------------------------------------------------------------------------
ALLOWED_USERS = {
    "관리자": "1234",
    "홍길동": "240101",
    "김철수": "240102",
    "이영희": "240103"
}

# --------------------------------------------------------------------------
# [2] 구글 시트 주소 (매니저님의 시트 주소를 넣었습니다)
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
        
        # [수정된 부분] 괄호가 잘리지 않도록 주의하세요!
        # 순서: [날짜, 부서, 성명, 직급, 질문, 답변, 비고]
        sheet.append_row([now, dept, name, rank, question, answer, ""]) 
        
        print(f"✅ 기록 완료: {dept} {name} {rank}")
        
    except Exception as e:
        st.error(f"기록 실패: {e}")

# 4. 로그인 화면
def login():
    st.header("🔒 임직원 접속 (신원확인)")
    st.caption("기록 관리를 위해 소속 정보를 정확히 입력해주세요.")
    
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        input_dept = col1.text_input("부서명", placeholder="예: 경영지원팀")
        input_rank = col2.text_input("직급", placeholder="예: 대리")
        
        input_name = st.text_input("성명", placeholder="이름을 입력하세요")
        input_id = st.text_input("사번 (비밀번호)", type="password")
        
        submit_button = st.form_submit_button("접속하기")
        
        if submit_button:
            if not input_dept or not input_rank or not input_name or not input_id:
                st.warning("모든 정보를 입력해주세요.")
                return

            if input_name in ALLOWED_USERS and ALLOWED_USERS[input_name] == input_id:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {
                    "dept": input_dept,
                    "name": input_name,
                    "rank": input_rank
                }
                st.success(f"{input_name} {input_rank}님, 환영합니다!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("성명 또는 사번이 일치하지 않습니다.")

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
