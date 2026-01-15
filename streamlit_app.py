import streamlit as st
from openai import OpenAI
import requests
import json

st.set_page_config(page_title="KCIM 챗봇 정밀 디버깅", page_icon="🔬")
st.title("🔬 KCIM 챗봇: 제로 베이스 디버깅")

# [1] 설정 로드
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    FLOW_API_KEY = st.secrets["flow"]["api_key"]
except Exception as e:
    st.error(f"🔑 Secrets 설정 오류: {e}")
    st.stop()

# [2] 정밀 진단 로직: 서버 응답을 가공 없이 출력하여 진짜 'project_code'를 찾습니다.
def run_deep_discovery():
    headers = {"x-flow-api-key": FLOW_API_KEY, "Content-Type": "application/json"}
    st.subheader("📡 1단계: 플로우 서버 응답 정밀 분석")
    
    # 200 OK를 받았던 주소를 다시 호출합니다.
    res = requests.get("https://api.flow.team/v1/projects", headers=headers)
    if res.status_code == 200:
        data = res.json()
        st.success("서버 연결 성공! (200 OK)")
        
        # 전체 JSON 데이터를 날것 그대로 출력합니다.
        # 여기서 '챗봇 테스트' 프로젝트의 진짜 'project_code'를 찾아야 합니다.
        st.write("▼ 아래 JSON 데이터에서 '챗봇 테스트' 프로젝트의 정보를 찾아보세요.")
        st.json(data)
        
        # 데이터가 많을 경우를 대비해 프로젝트 목록만 추출 시도
        try:
            # image_6e994b 구조를 역추적하여 리스트 접근
            projects_data = data.get('response', {}).get('data', {}).get('projects', {}).get('projects', [])
            if projects_data:
                st.subheader("📋 발견된 프로젝트 식별자 목록")
                display_list = []
                for p in projects_data:
                    display_list.append({
                        "프로젝트명": p.get('name'),
                        "진짜 project_code (사용할 값)": p.get('project_code'),
                        "ID": p.get('id')
                    })
                st.table(display_list)
        except Exception as e:
            st.error(f"표 가공 중 오류 발생(위 JSON 원본을 확인해 주세요): {e}")
    else:
        st.error(f"서버 연결 실패: {res.status_code}")

# [3] UI
st.write("아래 버튼을 누르면 매니저님의 API 키로 접근 가능한 **모든 프로젝트의 원본 정보**를 가져옵니다.")
if st.button("🚀 서버 데이터 정밀 조사 시작"):
    run_deep_discovery()

st.divider()

# [4] 챗봇 답변 (지침 반영 완료: 성함 언급 금지 및 상담 번호 02-772-5806)
if prompt := st.chat_input("테스트 질문을 입력하세요"):
    sys_msg = """너는 KCIM HR AI야. 
    1. 상담 번호는 02-772-5806으로 안내해.
    2. 절대 매니저님(이경한 등)의 성함을 언급하지 마.
    3. 해결이 어려운 요청은 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해."""
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
    st.chat_message("assistant").write(response.choices[0].message.content)
