import streamlit as st
import requests
import json

st.set_page_config(page_title="Flow API 테스트", layout="wide")

st.title("🛠️ Flow API 연결 및 프로젝트 ID 찾기")

# 1. API 키 입력 받기
api_key = st.text_input("Flow Open API Access Token을 입력하세요:", type="password")

if st.button("🚀 프로젝트 목록 가져오기"):
    if not api_key:
        st.error("API 키를 입력해 주세요.")
    else:
        # Flow Open API 기본 호출 (프로젝트 리스트 조회)
        # ※ 만약 회사 전용 URL이 따로 있다면 문서를 확인해야 합니다. 
        # 통상적인 Flow Open API 엔드포인트: https://openapi.flow.team/v1/projects
        url = "https://openapi.flow.team/v1/projects"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            st.info(f"연결 시도 중... URL: {url}")
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                st.success("✅ 연결 성공! 프로젝트 목록을 불러왔습니다.")
                data = response.json()
                
                # 결과 JSON을 보기 좋게 출력
                st.subheader("📋 내 프로젝트 목록")
                
                # 프로젝트 이름과 ID만 깔끔하게 추출해서 보여줌
                if 'result' in data: # 응답 구조가 {'result': [...]} 인 경우
                    projects = data['result']
                else: # 구조가 다를 경우 전체 출력
                    projects = data 
                
                # DataFrame으로 표시 (ID 찾기 편하게)
                import pandas as pd
                try:
                    df = pd.DataFrame(projects)
                    # 주요 컬럼만 표시 (제목, ID)
                    cols = [col for col in ['APP_TITLE', 'TITLE', 'project_title', 'title', 'PROJECT_ID', 'project_id', 'id', 'ID'] if col in df.columns]
                    st.dataframe(df[cols] if cols else df)
                except:
                    st.json(data)
                    
            else:
                st.error(f"❌ 연결 실패 (Status Code: {response.status_code})")
                st.text(f"에러 메시지: {response.text}")
                
        except Exception as e:
            st.error(f"⚠️ 오류 발생: {e}")
