import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="KCIM Flow API 연결", layout="centered")

st.markdown("## 🏢 KCIM 전용 Flow API 연결")
st.success("✅ 회사 도메인 확인됨: `kcim.flow.team`")

# 1. API 키 입력
api_key = st.text_input("Flow Access Token (API 키)를 입력하세요:", type="password")

if st.button("🚀 프로젝트 ID 찾기 (실행)"):
    if not api_key:
        st.error("API 키를 입력해주세요.")
    else:
        # KCIM 전용 API 주소 (가장 유력)
        target_url = "https://kcim.flow.team/api/v1/projects"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            st.info(f"접속 시도 중... {target_url}")
            response = requests.get(target_url, headers=headers, timeout=10)

            if response.status_code == 200:
                st.balloons()
                st.success("🎉 연결 성공! 데이터를 가져왔습니다.")
                
                data = response.json()
                
                # 데이터 파싱 (result 안에 있는지, 바로 리스트인지 확인)
                projects = data.get('result', data)
                
                if isinstance(projects, list):
                    # 보기 좋게 DataFrame으로 변환
                    df = pd.DataFrame(projects)
                    
                    # 필요한 컬럼만 추려서 보여줌 (제목, ID)
                    cols_to_show = []
                    for col in ['TITLE', 'project_title', 'title', 'PROJECT_TITLE', 'PROJECT_ID', 'project_id', 'id', 'ID']:
                        if col in df.columns:
                            cols_to_show.append(col)
                    
                    if cols_to_show:
                        st.dataframe(df[cols_to_show], use_container_width=True)
                    else:
                        st.dataframe(df) # 컬럼 못 찾으면 전체 표시
                        
                    st.markdown("### 👇 위 표에서 아래 프로젝트의 'ID' 숫자를 찾아 알려주세요!")
                    st.markdown("- **[KCIM] 전체 공지사항**")
                    st.markdown("- **[경영본부] HR팀**")
                else:
                    st.json(data)
            else:
                st.error(f"❌ 연결 실패 (상태 코드: {response.status_code})")
                st.code(response.text)

        except Exception as e:
            st.error(f"⚠️ 오류 발생: {e}")
