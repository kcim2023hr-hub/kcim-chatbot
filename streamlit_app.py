import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import traceback

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🤖")
st.title("🤖 KCIM 사내 민원/문의 챗봇")
st.markdown("---")

# 2. 비밀번호(Secrets) 불러오기
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

# --------------------------------------------------------------------------
# [필수] 여기에 구글 시트 주소 전체를 붙여넣으세요!
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603" 

# 3. 구글 시트 연결 함수 (이름으로 찾기 & 칸 맞추기)
def save_to_sheet(question, answer):
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        
        # [수정 1] 매니저님이 정하신 "응답시트"라는 이름을 정확히 찾아갑니다.
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        
        # [수정 2] 엑셀 헤더 순서(날짜, 요청자, 질문, 답변, 결과)에 맞춰서 저장합니다.
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 저장 순서: [A열:날짜, B열:빈칸(요청자), C열:질문, D열:답변, E열:빈칸(처리결과)]
        sheet.append_row([now, "", question, answer, ""]) 
        
        print("✅ 구글 시트 저장 완료")
        
    except Exception as e:
        st.error(f"구글 시트 저장 실패: {e}")
        st.text(traceback.format_exc())

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
        system_instruction = "너는 KCIM의 민원챗봇이야. 모르는 내용은 '담당자 확인 후 처리해 드리겠습니다'라고 답하고 끝에 [민원접수]라고 붙여."
        
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
