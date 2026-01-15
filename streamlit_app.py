import streamlit as st
from openai import OpenAI
import requests
import json
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 사내 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 설정 및 채팅방 자동 추적 (309개 전수 조사 로직)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    FLOW_API_KEY = st.secrets["flow"]["api_key"]
except Exception as e:
    st.error(f"🔑 설정 오류: {e}")
    st.stop()

def get_target_room_code():
    """309개 프로젝트를 전수 조사하여 '[민원챗봇] 수신전용프로젝트'의 채팅방 코드를 찾음"""
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    url = "https://api.flow.team/v1/projects" # 목록은 프로젝트 API로 가져옵니다.
    next_cursor = None
    
    # 309개 대응을 위해 최대 10페이지까지 조사
    for _ in range(10):
        params = {"cursor": next_cursor} if next_cursor else {}
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            p_data = data.get('response', {}).get('data', {}).get('projects', {})
            p_list = p_data.get('projects', [])
            
            # 실제 프로젝트 이름으로 채팅방 식별자 검색
            for p in p_list:
                p_name = str(p.get('name'))
                if "[민원챗봇] 수신전용프로젝트" in p_name:
                    # 프로젝트의 project_code가 채팅방의 room_code와 동일하게 쓰입니다.
                    return p.get('project_code')
            
            if not p_data.get('hasNext'): break
            next_cursor = p_data.get('lastCursor')
        else: break
    return None

def send_flow_chat_message(category, question, user_name):
    """게시글이 아닌 '채팅 메시지'를 전송 (OperationID: createChatMessage)"""
    room_code = get_target_room_code()
    if not room_code: return False, "플로우 채팅방을 찾을 수 없습니다."
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": FLOW_API_KEY}
    
    # ★ 404 해결을 위한 채팅 메시지 전용 주소 및 데이터 규격
    url = "https://api.flow.team/v1/messages"
    payload = {
        "room_code": room_code,
        "content": f"[🚨 {category} 채팅 알림]\n- 요청자: {user_name}\n- 내용: {question}\n- 접수일시: {datetime.now().strftime('%m/%d %H:%M')}"
    }
    
    res = requests.post(url, json=payload, headers=headers)
    # 성공 시 200 응답
    return (True, "성공") if res.status_code == 200 else (False, f"실패({res.status_code})")

# --------------------------------------------------------------------------
# [2] UI 및 챗봇 로직 (성함 언급 금지, 번호 02-772-5806 지침 준수)
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
    1. 답변 시 절대 담당자의 성함(이경한 등)을 직접 언급하지 마. 
    2. 직접 해결이 어려운 요청은 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
    3. 상담 안내 번호는 02-772-5806으로 안내해.
    """
    
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
        ans = response.choices[0].message.content
        
        # 민원 성격의 키워드 감지 시 채팅 알림 전송
        if any(kw in prompt for kw in ["수리", "고장", "신청", "시설", "불편"]):
            send_flow_chat_message("민원", prompt, "임직원")

        st.session_state.messages.append({"role": "assistant", "content": ans})
        st.chat_message("assistant").write(ans)
    except Exception as e: st.error(f"오류: {e}")

# 관리자용 테스트 도구
with st.sidebar:
    st.markdown("### 🛠️ 관리자 도구")
    if st.button("💬 채팅 메시지 연동 테스트"):
        with st.status("채팅방 탐색 및 전송 시도 중...") as s:
            ok, msg = send_flow_chat_message("시스템 테스트", "채팅 메시지 연동에 성공했습니다!", "관리자")
            if ok: s.update(label="✅ 채팅 전송 성공! 플로우를 확인하세요.", state="complete")
            else: st.error(msg)
