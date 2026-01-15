import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import traceback
import time

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="ew")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 직원 명단 (이곳에 실제 임직원 정보를 입력하세요)
# 형식: "이름": "사번(또는 비밀번호)"
# --------------------------------------------------------------------------
ALLOWED_USERS = {
    "관리자": "1234",
    "홍길동": "240101",
    "김철수": "240102",
    "이영희": "240103"
}

# --------------------------------------------------------------------------
# [2] 구글 시트 주소 (매니저님의 주소로 변경해주세요)
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603"


# 3. 비밀번호(Secrets) 불러오기
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

# 4. 구글 시트 연결 함수 (요청자 이름 포함)
def save_to_sheet(user_name, question, answer):
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        
        # 시트 열기
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        
        # 날짜 및 저장
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # [업그레이드] B열에 'user_name(민원요청자)'을 기록합니다.
        # 순서: [날짜, 민원요청자, 민원내용, 답변내용, 처리결과]
        sheet.append_row([now, user_name, question, answer, ""]) 
        
    except Exception as e:
        st.error(f"기록 실패: {e}")

# 5. 로그인 화면 함수
def login():
    st.subheader("🔒 임직원 신원 확인")
    
    with st.form("login_form"):
        input_name = st.text_input("성명", placeholder="이름을 입력하세요 (예: 홍길동)")
        input_id = st.text_input("사번", placeholder="사번을 입력하세요 (예: 240101)", type="password")
        
        submit_button = st.form_submit_button("접속하기")
        
        if submit_button:
            # 명단 확인 로직
            if input_name in ALLOWED_USERS and ALLOWED_USERS[input_name] == input_id:
                st.session_state["logged_in"] = True
                st.session_state["user_name"] = input_name
                st.success(f"{input_name}님, 환영합니다!")
                time.sleep(1)
                st.rerun() # 화면 새로고침
            else:
                st.error("성명 또는 사번이 일치하지 않습니다. 다시 확인해주세요.")

# 6. 메인 로직 (로그인 여부에 따라 화면 분기)
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    # 로그인이 안 되어 있으면 로그인 화면 보여주기
    login()
else:
    # 로그인 되었으면 채팅 화면 보여주기
    st.markdown(f"**반갑습니다, {st.session_state['user_name']}님!** (KCIM HR팀)")
    if st.button("로그아웃"):
        st.session_state["logged_in"] = False
        st.rerun()
    st.markdown("---")

    # 채팅 로직
    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "무엇을 도와드릴까요? (규정 문의, 민원 접수 등)"}]

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        response = ""
        try:
            # KCIM 규정
            system_instruction = """
            너는 건설IT 솔루션 전문기업 'KCIM(케이씨아이엠)'의 HR/총무 담당 AI 매니저야.
            임직원의 질문에 대해 아래 [사내 규정]을 기반으로 친절하고 명확하게 답변해.
            
            [사내 규정 데이터베이스]
            1. 법인차량 사용: 그룹웨어 > 자원관리 > 차량예약 (키 수령: 3층 경영지원팀)
            2. 연차 규정: 팀장 전결 (3일 이상 본부장), 반차 사용 가능.
            3. 경조사: 결혼(본인 50/5일, 자녀 30/3일). 1주일 전 신청서 제출.
            4. 기타 민원: 담당자 확인이 필요한 사항은 "담당자 확인 후 처리해 드리겠습니다."라고 답하고 끝에 [민원접수] 태그를 붙여.
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
        
        # [핵심] 기록할 때 로그인한 사람의 이름(st.session_state["user_name"])을 같이 보냄
        save_to_sheet(st.session_state["user_name"], prompt, response)
