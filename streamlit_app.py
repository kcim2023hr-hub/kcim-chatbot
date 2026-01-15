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

# [2] 정밀 진단 로직: 서버 응답을 가공 없이 출력
def run_discovery():
    headers = {"x-flow-api-key": FLOW_API_KEY, "Content-Type": "application/json"}
    st.subheader("📡 1단계: 플로우 서버 응답 원본 확인")
    
    # 이전에 200 OK를 받았던 주소를 다시 호출합니다.
    res = requests.get("https://api.flow.team/v1/projects", headers=headers)
    if res.status_code == 200:
        data = res.json()
        st.success("서버 연결 성공! (200 OK)")
        
        # 전체 JSON 데이터를 그대로 출력하여 구조를 파악합니다.
        with st.expander("원본 JSON 데이터 보기 (클릭하여 확장)"):
            st.json(data)
            
        # 프로젝트 목록 추출 시도
        try:
            # image_6e994b 구조에 따른 접근
            projects_list = data.get('response', {}).get('data', {}).get('projects', {}).get('projects', [])
            if projects_list:
                st.subheader("📋 발견된 프로젝트 목록")
                # 모든 프로젝트의 코드와 이름을 표로 표시
                display_list = []
                for p in projects_list:
                    display_list.append({
                        "프로젝트명": p.get('name'),
                        "진짜 project_code (이것을 사용해야 함)": p.get('project_code'),
                        "ID": p.get('id')
                    })
                st.table(display_list)
            else:
                st.warning("JSON 구조는 맞으나 프로젝트 리스트가 비어 있습니다.")
        except Exception as e:
            st.error(f"데이터 파싱 오류: {e}")
    else:
        st.error(f"서버 연결 실패: {res.status_code}")

# [3] UI
st.write("아래 버튼을 누르면 매니저님의 API 키로 접근 가능한 **모든 프로젝트의 진짜 정보**를 가져옵니다.")
if st.button("🚀 서버 데이터 정밀 조사 시작"):
    run_discovery()

st.divider()

# [4] 챗봇 답변 (지침 반영: 성함 언급 금지 및 상담 번호 02-772-5806)
if prompt := st.chat_input("테스트 질문을 입력하세요"):
    sys_msg = """너는 KCIM HR AI야. 
    1. 상담 번호는 02-772-5806으로 안내해. 
    2. 절대 매니저님(이경한 등)의 성함을 직접 언급하지 마. 
    3. 해결이 어려운 요청은 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해."""
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
    st.chat_message("assistant").write(response.choices[0].message.content)
