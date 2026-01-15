import streamlit as st
from openai import OpenAI
import requests
import json
import pandas as pd

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 챗봇 최종본", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드 (전화번호 02-772-5806 반영)
# --------------------------------------------------------------------------
@st.cache_data
def load_db():
    # 상담 안내 번호 업데이트 완료: 02-772-5806
    return {"관리자": {"pw": "1323", "dept": "HR팀", "rank": "매니저", "tel": "02-772-5806"}}

# --------------------------------------------------------------------------
# [2] 외부 연동 (Flow 프로젝트 자동 추적 및 전송 로직)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    FLOW_API_KEY = st.secrets["flow"]["api_key"]
except Exception as e:
    st.error(f"🔑 설정 오류: {e}")
    st.stop()

def auto_send_flow(category, question, user_name):
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    
    # 1단계: 309개 프로젝트 중 '챗봇 테스트' 방의 진짜 코드 찾기
    try:
        res = requests.get("https://api.flow.team/v1/projects", headers=headers)
        if res.status_code == 200:
            data = res.json()
            # 서버 응답 구조 정밀 추적 (response -> data -> projects -> projects)
            p_list = data.get('response', {}).get('data', {}).get('projects', {}).get('projects', [])
            
            # '챗봇 테스트'라는 이름의 프로젝트 검색
            target_project = next((p for p in p_list if "챗봇 테스트" in str(p.get('name'))), None)
            
            if target_project:
                real_code = target_project.get('project_code') # 진짜 식별자 추출
                
                # 2단계: 찾은 코드로 즉시 게시글 전송
                url = "https://api.flow.team/v1/posts"
                payload = {
                    "project_code": real_code,
                    "title": f"🚨 챗봇 민원 접수 ({category})",
                    "body": f"- 요청자: {user_name}\n- 내용: {question}"
                }
                requests.post(url, json=payload, headers=headers)
                return True
    except: pass
    return False

# --------------------------------------------------------------------------
# [3] UI 및 챗봇 로직 (지침 준수: 성함 언급 금지, 번호 고정)
# --------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 **02-772-5806**로 문의하시거나 여기서 질문해 주세요."}]

for msg in st.session_state.messages: st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("질문을 입력하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # 시스템 지침: 이경한 매니저 성함 언급 절대 금지
    sys_msg = """너는 KCIM HR AI야. 
    1. 답변 시 절대 담당자의 성함(이경한 등)을 언급하지 마. 
    2. 직접 해결이 어려운 요청은 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
    3. 상담 안내 번호는 02-772-5806으로 안내해.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}]
        )
        ans = response.choices[0].message.content
        
        # 시설/수리 등 담당자 확인이 필요한 경우 자동 전송
        if any(keyword in prompt for keyword in ["수리", "고장", "신청", "시설"]):
            auto_send_flow("시설문의", prompt, "임직원")

        st.session_state.messages.append({"role": "assistant", "content": ans})
        st.chat_message("assistant").write(ans)
    except Exception as e: st.error(f"오류: {e}")

# 관리자 전용 테스트 버튼
with st.sidebar:
    st.markdown("### 🛠️ 관리자 도구")
    if st.button("🔔 연동 자동 확인"):
        with st.status("프로젝트 탐색 및 전송 시도 중...") as s:
            if auto_send_flow("테스트", "자동 추적 연동 성공!", "관리자"):
                s.update(label="✅ 전송 성공! 플로우를 확인하세요.", state="complete")
            else:
                s.update(label="❌ 실패: 프로젝트를 찾을 수 없음", state="error")
