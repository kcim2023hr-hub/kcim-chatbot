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

# [2] 정밀 진단 로직: 모든 프로젝트의 '진짜 ID'와 '코드'를 추출
def run_discovery():
    headers = {"x-flow-api-key": FLOW_API_KEY, "Content-Type": "application/json"}
    st.subheader("📡 1단계: 플로우 서버 응답 정밀 분석")
    
    # 200 OK가 났던 그 주소를 다시 호출합니다.
    res = requests.get("https://api.flow.team/v1/projects", headers=headers)
    if res.status_code == 200:
        data = res.json()
        projects = data.get('response', {}).get('data', {}).get('projects', {}).get('projects', [])
        
        if not projects:
            st.warning("목록은 가져왔으나 참여 중인 프로젝트가 하나도 없습니다.")
            return
        
        # 전체 프로젝트 목록을 테이블로 시각화하여 진짜 'project_code'를 찾습니다.
        st.write("▼ 아래 표에서 **'챗봇 테스트'** 프로젝트의 **project_code**를 확인해 주세요.")
        display_data = []
        for p in projects:
            display_data.append({
                "프로젝트 이름": p.get('name'),
                "진짜 project_code (이게 필요함)": p.get('project_code'),
                "ID": p.get('id')
            })
        st.table(display_data)
        
        # 발견된 코드로 즉시 전송 테스트
        st.subheader("📡 2단계: 확인된 코드로 전송 테스트")
        for p in display_data:
            code = p["진짜 project_code (이게 필요함)"]
            if p["프로젝트 이름"] == "챗봇 테스트" or code == "2786111":
                url = "https://api.flow.team/v1/posts"
                payload = {"project_code": code, "title": "🔬 디버깅 테스트", "body": "연동 성공을 기원합니다."}
                st.write(f"👉 프로젝트 [{p['프로젝트 이름']}]에 전송 시도 중...")
                r = requests.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    st.balloons()
                    st.success(f"✅ 드디어 성공했습니다! 주소: {url} / 코드: {code}")
                else:
                    st.error(f"❌ 실패 ({r.status_code})")
                    st.json(r.text)
    else:
        st.error(f"❌ 서버 연결 실패: {res.status_code}")

# [3] UI
if st.button("🚀 서버 데이터 정밀 조사 시작"):
    run_discovery()

st.divider()

# [4] 챗봇 답변 (지침 반영 완료)
if prompt := st.chat_input("테스트 질문을 입력하세요"):
    sys_msg = """너는 KCIM HR AI 매니저야.
    1. 상담 번호는 02-772-5806으로 안내해.
    2. 절대 담당자 개인의 성함을 언급하지 마.
    3. 해결이 어려운 요청은 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
    st.chat_message("assistant").write(response.choices[0].message.content)
