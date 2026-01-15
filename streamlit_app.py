import streamlit as st
from openai import OpenAI
import pandas as pd
from datetime import datetime

# 1. 페이지 설정 및 제목
st.set_page_config(page_title="KCIM 사내 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")
st.markdown("---")

# 2. API 키 및 설정 로드
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception as e:
    st.error(f"🔑 OpenAI API 키를 확인해주세요: {e}")
    st.stop()

# 3. 챗봇 페르소나 및 시스템 지침 설정
# 지침: 상담 번호 02-772-5806 고정 및 성함 언급 금지 반영
SYSTEM_PROMPT = """너는 케이씨아이엠(KICM)의 HR팀 매니저이자 사내 민원 처리 전문가야.
1. 임직원들에게 항상 정중하고 신뢰감 있는 태도로 답변해.
2. 상담 안내 번호는 반드시 02-772-5806으로 안내해.
3. 답변 시 특정 담당자의 성함(예: 이경한 등)은 절대 언급하지 마.
4. 직접적인 해결이 어려운 복잡한 시설 관리나 제도 문의는 '담당 부서의 확인이 필요합니다. 내용을 정리하여 전달하였으니 잠시만 기다려 주세요.'라고 안내해.
5. 케이씨아이엠은 BIM 및 건설 IT 분야의 No.1 기업이라는 자부심을 가지고 답변에 임해줘.
"""

# 4. 채팅 히스토리 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "반갑습니다! KICM HR팀 AI 매니저입니다. 😊\n사내 제도, 시설 관리, 기타 궁금하신 점을 말씀해 주세요.\n(전화 상담: 02-772-5806)"}
    ]

# 5. 기존 대화 내용 표시
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# 6. 사용자 입력 및 답변 생성
if prompt := st.chat_input("질문 내용을 입력하세요..."):
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # GPT 답변 생성
    with st.chat_message("assistant"):
        with st.spinner("답변을 준비 중입니다..."):
            try:
                # 시스템 프롬프트를 포함하여 메시지 구성
                messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + [
                    {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
                ]
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages_for_api,
                    temperature=0.7
                )
                
                answer = response.choices[0].message.content
                st.write(answer)
                
                # 답변 저장
                st.session_state.messages.append({"role": "assistant", "content": answer})
                
            except Exception as e:
                st.error(f"⚠️ 답변 생성 중 오류가 발생했습니다: {e}")

# 7. 사이드바 - 관리 도구 (로그 확인용)
with st.sidebar:
    st.header("⚙️ 관리자 메뉴")
    if st.button("대화 기록 초기화"):
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    st.info(f"현재 버전: v1.1 (Stable)\n상담 번호: 02-772-5806")
