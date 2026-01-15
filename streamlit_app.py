import streamlit as st
from openai import OpenAI
import requests
import json
from datetime import datetime

st.set_page_config(page_title="KCIM 챗봇 디버깅", page_icon="🛠️")
st.title("🛠️ Flow API 엔드포인트 디버깅 도구")

# [1] 설정 로드
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    FLOW_API_KEY = st.secrets["flow"]["api_key"]
    PROJECT_ID = "2786111" # 확인된 프로젝트 ID
except Exception as e:
    st.error(f"🔑 Secrets 설정 오류: {e}")
    st.stop()

# [2] 디버깅용 전송 함수
def debug_flow_post(url, payload, label):
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    st.write(f"🔍 **[{label}] 시도 중...**")
    st.code(f"URL: {url}")
    
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            st.success(f"✅ [{label}] 성공! (200 OK)")
            return True
        else:
            st.error(f"❌ [{label}] 실패 ({res.status_code})")
            st.json(res.text)
            return False
    except Exception as e:
        st.error(f"⚠️ 에러 발생: {e}")
        return False

# [3] 관리자 도구 UI
st.divider()
if st.button("🚀 모든 엔드포인트 동시 테스트"):
    content = f"디버깅 테스트 메시지 ({datetime.now().strftime('%H:%M:%S')})"
    
    # 시도 1: 관리자 표준 (project_code를 본문에 포함)
    debug_flow_post(
        "https://api.flow.team/v1/posts",
        {"project_code": PROJECT_ID, "title": "🤖 디버깅 알림", "body": content},
        "패턴 A (전역 경로)"
    )
    
    # 시도 2: 프로젝트 하위 경로
    debug_flow_post(
        f"https://api.flow.team/v1/projects/{PROJECT_ID}/posts",
        {"title": "🤖 디버깅 알림", "body": content},
        "패턴 B (프로젝트 하위)"
    )

st.divider()

# [4] 챗봇 대화 로직 (지침 반영)
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("질문하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # 지침: 성함 언급 금지 및 상담 번호 02-772-5806 반영
    sys_msg = f"""너는 KCIM HR AI야. 
    1. 답변 시 절대 '이경한 매니저' 성함을 언급하지 마. 
    2. 대신 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
    3. 상담 안내 번호는 반드시 02-772-5806으로 안내해.
    """
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
    ans = response.choices[0].message.content
    
    st.session_state.messages.append({"role": "assistant", "content": ans})
    st.chat_message("assistant").write(ans)
