import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Flow API 진단기", layout="centered")

st.markdown("## 🩺 Flow API 연결 정밀 진단")
st.info("발급받으신 API 토큰을 입력하고 연결 버튼을 눌러주세요.")

# 1. API 키 입력
api_key = st.text_input("Flow Access Token", type="password", placeholder="ey...")

# 2. 테스트할 API 주소 후보 (가장 유력한 2가지)
endpoints = [
    ("공식 Open API", "https://openapi.flow.team/v1/projects"),
    ("레거시 API", "https://flow.team/api/v1/projects")
]

if st.button("🔍 연결 테스트 시작"):
    if not api_key:
        st.error("API 키를 입력해주세요!")
    else:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        success = False
        
        for name, url in endpoints:
            st.markdown(f"--- \n### 📡 시도 중: **{name}**")
            st.text(f"URL: {url}")
            
            try:
                response = requests.get(url, headers=headers, timeout=5)
                
                # 결과 출력
                st.write(f"**상태 코드:** `{response.status_code}`")
                
                if response.status_code == 200:
                    st.success(f"✅ {name} 연결 성공!")
                    data = response.json()
                    
                    # 프로젝트 목록 파싱 시도
                    projects = data.get('result', data) if isinstance(data, dict) else data
                    
                    if isinstance(projects, list) and len(projects) > 0:
                        st.dataframe(pd.DataFrame(projects))
                        st.balloons()
                    else:
                        st.warning("연결은 됐지만 프로젝트 목록이 비어있거나 형식이 다릅니다.")
                        st.json(data)
                    success = True
                    break # 성공하면 중단
                    
                else:
                    st.error("❌ 연결 실패")
                    st.code(response.text) # 에러의 구체적인 원인 출력
            
            except Exception as e:
                st.error(f"⚠️ 요청 중 오류 발생: {e}")

        if not success:
            st.error("모든 주소 연결에 실패했습니다. 에러 메시지를 복사해서 알려주세요.")
