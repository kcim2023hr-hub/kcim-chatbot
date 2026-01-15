import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="KICM 민원 챗봇", page_icon="🤖")
st.title("🤖 KICM 사내 민원/문의 챗봇")
st.markdown("---")

# 2. 비밀번호(Secrets) 불러오기
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

# --------------------------------------------------------------------------
# [수정 포인트] 따옴표("") 안에 엑셀 주소를 넣어야 합니다!
# 실수하지 않도록 제가 따옴표를 미리 적어두었습니다.
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603" 

# 3. 구글 시트 연결 함수
def save_to_sheet(question, answer):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        
        # URL로 시트 찾기
        sheet = gs_client.open_by_url(sheet_url).sheet1
        
        # 기록
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, question, answer])
        
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")

# 4. 챗봇 로직
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "안녕하세요! KICM 총무/HR 지원 챗봇입니다. 무엇을 도와드릴까요?"}]

# 이전 대화 출력
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# 사용자 입력 처리
if prompt := st.chat_input("질문을 입력하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    response = ""
    try:
        system_instruction = "너는 KICM의 HR 매니저야. 모르는 내용은 '담당자 확인 후 처리해 드리겠습니다'라고 답하고 끝에 [민원접수]라고 붙여."
        
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
    
    # 구글 시트에 기록
    save_to_sheet(prompt, response)
