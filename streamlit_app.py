import streamlit as st
from openai import OpenAI
import requests
import json
import pandas as pd

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 챗봇 최종형", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 설정 및 외부 연동 (Pagination 해결 로직)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    FLOW_API_KEY = st.secrets["flow"]["api_key"]
except Exception as e:
    st.error(f"🔑 설정 오류: {e}")
    st.stop()

def get_real_project_code():
    """309개 이상의 프로젝트를 모두 뒤져서 '챗봇 테스트' 코드를 찾음"""
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    url = "https://api.flow.team/v1/projects"
    all_projects = []
    next_cursor = None
    
    # 최대 5페이지(500개)까지 전수 조사
    for _ in range(5):
        params = {"cursor": next_cursor} if next_cursor else {}
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            # response -> data -> projects -> projects 계층 파고들기
            p_data = data.get('response', {}).get('data', {}).get('projects', {})
            all_projects.extend(p_data.get('projects', []))
            
            # 다음 페이지가 있는지 확인
            if not p_data.get('hasNext'): break
            next_cursor = p_data.get('lastCursor')
        else: break
            
    # '챗봇 테스트' 이름을 가진 프로젝트 찾기
    target = next((p for p in all_projects if "챗봇 테스트" in str(p.get('name'))), None)
    return target.get('project_code') if target else None

def send_flow_post(category, question, user_name):
    p_code = get_real_project_code()
    if not p_code: return False, "309개 중 '챗봇 테스트' 프로젝트를 찾지 못했습니다."
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    url = "https://api.flow.team/v1/posts"
    payload = {
        "project_code": p_code,
        "title": f"🚨 챗봇 민원 접수 ({category})",
        "body": f"- 요청자: {user_name}\n- 내용: {question}"
    }
    res = requests.post(url, json=payload, headers=headers)
    return (True, "성공") if res.status_code == 200 else (False, f"실패({res.status_code}): {res.text}")

# --------------------------------------------------------------------------
# [2] UI 및 챗봇 로직 (지침 준수: 성함 언급 금지, 번호 02-772-5806 고정)
# --------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 문의사항은 **02-772-5806**으로 연락주시거나 여기에 남겨주세요."}]

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
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
        ans = response.choices[0].message.content
        
        # 담당자 확인 필요 키워드 시 자동 알림 전송
        if any(kw in prompt for kw in ["수리", "고장", "신청", "시설", "불편"]):
            send_flow_post("자동민원", prompt, "임직원")

        st.session_state.messages.append({"role": "assistant", "content": ans})
        st.chat_message("assistant").write(ans)
    except Exception as e: st.error(f"오류: {e}")

# 관리자 디버깅 도구
with st.sidebar:
    st.markdown("### 🛠️ 관리자 도구")
    if st.button("🔔 309개 프로젝트 전수 조사 및 테스트"):
        with st.status("전체 페이지 탐색 중...") as s:
            ok, msg = send_flow_alert = send_flow_post("테스트", "전수 조사 연동 성공!", "관리자")
            if ok: s.update(label="✅ 성공! 플로우를 확인하세요.", state="complete")
            else: st.error(msg)
