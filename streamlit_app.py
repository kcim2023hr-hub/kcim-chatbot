import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Flow API 최종 시도", layout="centered")
st.markdown("## 🔑 표준 API + 회사 코드 조합 테스트")

# 1. API 키 입력
api_key = st.text_input("Flow Access Token (API 키)", type="password")

if st.button("🚀 프로젝트 ID 찾기"):
    if not api_key:
        st.error("API 키를 입력해주세요.")
    else:
        # 표준 Open API 주소
        url = "https://openapi.flow.team/v1/projects"
        
        # 헤더 (인증키)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # ★ 핵심: 회사 코드를 파라미터로 같이 보냄 ★
        params = {
            "company_code": "kcim" 
        }

        try:
            st.info(f"접속 시도 중... {url} (Code: kcim)")
            response = requests.get(url, headers=headers, params=params, timeout=10)

            if response.status_code == 200:
                st.balloons()
                st.success("🎉 연결 성공! 드디어 뚫렸습니다!")
                
                data = response.json()
                projects = data.get('result', data)
                
                if isinstance(projects, list):
                    df = pd.DataFrame(projects)
                    # ID와 제목만 깔끔하게 표시
                    cols = [c for c in ['PROJECT_TITLE', 'project_title', 'TITLE', 'title', 'PROJECT_ID', 'project_id', 'id', 'ID'] if c in df.columns]
                    st.dataframe(df[cols] if cols else df)
                    st.write("👆 위 표에서 **'[KCIM] 전체 공지사항'**과 **'[경영본부] HR팀'**의 ID 숫자를 확인하세요!")
                else:
                    st.json(data)
            else:
                st.error(f"❌ 실패 (상태 코드: {response.status_code})")
                st.text(response.text) # 에러 메시지 확인

        except Exception as e:
            st.error(f"⚠️ 오류 발생: {e}")
