import streamlit as st
from openai import OpenAI
import requests
import json
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 사내 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 설정 및 프로젝트 자동 추적 (309개 전수 조사 로직)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    FLOW_API_KEY = st.secrets["flow"]["api_key"]
except Exception as e:
    st.error(f"🔑 설정 오류: {e}")
    st.stop()

def get_target_project_code():
    """309개 프로젝트를 페이지별로 모두 뒤져서 진짜 코드를 찾음"""
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    url = "https://api.flow.team/v1/projects"
    next_cursor = None
    
    # 309개 대응을 위해 최대 10페이지까지 전수 조사 시도
    for _ in range(10):
        params = {"cursor": next_cursor} if next_cursor else {}
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            # 서버 응답 구조 정밀 추적 (response -> data -> projects -> projects)
            p_data = data.get('response', {}).get('data', {}).get('projects', {})
            p_list = p_data.get('projects', [])
            
            # 매니저님의 실제 프로젝트 이름으로 검색
            for p in p_list:
                p_name = str(p.get('name'))
                if "[민원챗봇] 수신전용프로젝트" in p_name:
                    return p.get('project_code')
            
            if not p_data.get('hasNext'): break
            next_cursor = p_data.get('lastCursor')
        else: break
    return None

def send_flow_alert(category, question, user_name):
    p_code = get_target_project_code()
    if not p_code: return False, "플로우 프로젝트를 찾을 수 없습니다."
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    url = "https://api.flow.team/v1/posts"
    payload = {
        "project_code": p_code,
        "title": f"🚨 {category} 접수",
        "body": f"- 요청자: {user_name}\n- 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n- 내용: {question}"
    }
    res = requests.post(url, json=payload, headers=headers)
    return (True, "성공") if res.status_code == 200 else (False, f"실패({res.status_code})")

# --------------------------------------------------------------------------
# [2] UI 및 챗봇 로직 (지침 준수: 성함 언급 금지, 번호 02-772-5806)
# --------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 문의사항은 **02-772-5806**으로 연락주시거나 여기에 남겨주세요."}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("질문을 입력하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # 지침: 매니저님 성함 언급 절대 금지 및 안내 번호 고정
    sys_msg = """너는 KCIM HR AI 매니저야. 
    1. 답변 시 절대 담당자의 성함을 직접 언급하지 마. 
    2. 직접 해결이 어려운 요청은 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
    3. 상담 안내 번호는 02-772-5806으로 안내해.
    """
    
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
        ans = response.choices[0].message.content
        
        # 특정 키워드 포함 시 플로우 알림 자동 전송
        if any(kw in prompt for kw in ["수리", "고장", "신청", "시설", "불편"]):
            send_flow_alert("민원", prompt, "임직원")

        st.session_state.messages.append({"role": "assistant", "content": ans})
        st.chat_message("assistant").write(ans)
    except Exception as e: st.error(f"오류: {e}")

# 관리자 전용 테스트 버튼
with st.sidebar:
    st.markdown("### 🛠️ 관리자 도구")
    if st.button("🔔 연동 최종 테스트"):
        with st.status("309개 프로젝트 전수 조사 중...") as s:
            ok, msg = send_flow_alert("시스템 테스트", "연동이 드디어 최종 성공했습니다!", "관리자")
            if ok: s.update(label="✅ 전송 성공! 플로우를 확인하세요.", state="complete")
            else: st.error(msg)
