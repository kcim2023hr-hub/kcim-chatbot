import streamlit as st
from openai import OpenAI
import requests
import json
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="KCIM 챗봇 디버깅", page_icon="🛠️")
st.title("🛠️ KCIM 챗봇 API 최종 디버깅 도구")

# [1] 설정 로드
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    FLOW_API_KEY = st.secrets["flow"]["api_key"]
    # image_6cbc4f에서 확인된 ID. 만약 코드가 따로 있다면 아래 디버깅에서 발견될 것입니다.
    DEFAULT_PROJECT_ID = "2786111" 
except Exception as e:
    st.error(f"🔑 Secrets 설정 오류: {e}")
    st.stop()

# [2] 정밀 디버깅 함수
def run_deep_discovery():
    headers = {"x-flow-api-key": FLOW_API_KEY, "Content-Type": "application/json"}
    st.subheader("🔍 1단계: 프로젝트 정밀 분석")
    
    res = requests.get("https://api.flow.team/v1/projects", headers=headers)
    if res.status_code == 200:
        data = res.json()
        projects = data.get('response', {}).get('data', {}).get('projects', {}).get('projects', [])
        
        # 챗봇 테스트 프로젝트 찾기
        target = next((p for p in projects if p.get('name') == "챗봇 테스트" or p.get('project_code') == DEFAULT_PROJECT_ID), None)
        
        if target:
            st.success(f"🎯 '챗봇 테스트' 프로젝트를 찾았습니다!")
            st.json(target)
            # 프로젝트 코드 확인 (숫자 ID와 문자 Code가 다를 수 있음)
            p_code = target.get('project_code')
            
            st.subheader("🔍 2단계: 주소 규격 테스트")
            test_content = f"디버깅 전송 테스트 ({datetime.now().strftime('%H:%M:%S')})"
            
            # 테스트할 모든 주소 패턴
            patterns = [
                ("패턴 A (표준)", "https://api.flow.team/v1/posts", {"project_code": p_code, "title": "🤖 테스트", "body": test_content}),
                ("패턴 B (프로젝트 하위)", f"https://api.flow.team/v1/projects/{p_code}/posts", {"title": "🤖 테스트", "body": test_content}),
                ("패턴 C (메시지)", "https://api.flow.team/v1/messages", {"room_code": p_code, "content": test_content})
            ]
            
            for label, url, payload in patterns:
                st.write(f"📡 **{label} 시도...**")
                r = requests.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    st.balloons()
                    st.success(f"✅ {label} 성공!!! 진짜 주소를 찾았습니다: {url}")
                    return url, payload
                else:
                    st.warning(f"❌ {label} 실패 ({r.status_code})")
                    try: st.json(r.json())
                    except: st.write(r.text)
        else:
            st.error("❌ '챗봇 테스트' 프로젝트를 목록에서 찾을 수 없습니다. 프로젝트 이름을 확인해 주세요.")
    else:
        st.error(f"❌ 프로젝트 목록 로드 실패 ({res.status_code})")
    return None, None

# [3] 관리자 UI
with st.sidebar:
    st.header("⚙️ 디버깅 제어판")
    if st.button("🚀 주소 자동 찾기 시작"):
        run_deep_discovery()

# [4] 챗봇 답변 로직 (지침 반영)
st.divider()
st.info("챗봇 상담 안내 번호: 02-772-5806 (업데이트 완료)")

if prompt := st.chat_input("질문하세요"):
    # 지침 반영: 성함 언급 금지 및 안내 번호 고정
    sys_msg = """너는 KCIM HR AI 매니저야.
    1. 답변 시 절대 담당자의 성함(이경한 등)을 직접 언급하지 마. 
    2. 직접 해결이 어려운 요청은 '담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
    3. 상담 안내 번호는 02-772-5806으로 안내해.
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
    st.chat_message("assistant").write(response.choices[0].message.content)
