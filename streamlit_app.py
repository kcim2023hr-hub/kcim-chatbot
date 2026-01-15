import streamlit as st
from openai import OpenAI # 최신 버전 호환
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="KICM 민원 챗봇", page_icon="🤖")
st.title("🤖 KICM 사내 민원/문의 챗봇")
st.markdown("---")

# 2. 비밀번호(Secrets) 불러오기 및 설정
try:
    # 최신 OpenAI 라이브러리 사용 방식
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

# 3. 구글 시트 연결 함수
def save_to_sheet(question, answer):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        
        # 시트 열기 (시트 이름: KICM_민원관리)
        sheet = gs_client.open("KICM_민원관리").sheet1
        
        # 날짜, 질문, 답변 저장
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, question, answer])
    except Exception as e:
        print(f"구글 시트 저장 실패: {e}") 
        # 사용자에겐 에러를 보여주지 않고 넘어가도록 처리

# 4. 챗봇 로직
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "안녕하세요! KICM 총무/HR 지원 챗봇입니다. 궁금한 점을 물어보세요. (예: 법인차량 예약, 연차 규정)"}]

# 이전 대화 출력
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# 사용자 입력 처리
if prompt := st.chat_input("질문을 입력하세요"):
    # 사용자 메시지 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # AI 응답 생성
    response = ""
    try:
        # 시스템 프롬프트 (AI의 성격과 규칙 설정)
        system_instruction = """
        너는 KICM(케이씨아이엠)의 HR 및 총무 담당 AI 매니저야. 임직원들에게 친절하고 명확하게 답변해줘.
        
        [답변 가이드]
        1. 모르는 내용이나 현장 조치가 필요한 민원(예: 화장실 고장, 비품 구매)은 
           "담당자 확인 후 처리해 드리겠습니다."라고 답변하고 답변 끝에 반드시 [민원접수]라고 붙여.
        2. 답변은 3줄 이내로 간결하게 핵심만 말해.
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
        response = f"죄송합니다. 오류가 발생했습니다: {e}"

    # AI 메시지 표시
    st.session_state.messages.append({"role": "assistant", "content": response})
    st.chat_message("assistant").write(response)
    
    # 구글 시트에 기록
    save_to_sheet(prompt, response)
