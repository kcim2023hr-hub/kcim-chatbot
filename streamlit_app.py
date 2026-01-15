import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
import os
import re
import PyPDF2
import requests

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드 (02-772-5806 및 성함 언급 금지 정책 반영)
# --------------------------------------------------------------------------
@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    # 요청하신 상담 안내 번호 업데이트 완료 (02-772-5806)
    db["관리자"] = {"pw": "1323", "dept": "HR팀", "rank": "매니저", "tel": "02-772-5806"}
    if os.path.exists(file_name):
        try:
            df = pd.read_excel(file_name, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            for _, row in df.iterrows():
                try:
                    name = str(row['이름']).strip()
                    phone = str(row['휴대폰 번호']).strip()
                    phone_digits = re.sub(r'[^0-9]', '', phone)
                    pw = phone_digits[-4:] if len(phone_digits) >= 4 else "0000"
                    db[name] = {"pw": pw, "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
                except: continue
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except Exception as e: st.error(f"❌ 엑셀 로드 실패: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [2] 외부 연동 (Flow 관리자 API 표준 주소 적용으로 404 정면 돌파)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
    flow_secrets = st.secrets.get("flow", None)
except Exception as e:
    st.error(f"🔑 Secrets 설정 오류: {e}")
    st.stop()

def send_flow_alert(category, question, name, dept):
    if not flow_secrets: return False, "Secrets 설정 누락"
    api_key = flow_secrets.get("api_key")
    p_id = "2786111" # image_6cbc4f에서 확인된 ID
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": api_key}
    content = f"[🚨 챗봇 민원 알림]\n- 요청자: {name} ({dept})\n- 분류: {category}\n- 내용: {question}"

    # ★ 404 해결의 핵심: 등록하신 동작(OperationID)에 맞는 '표준 주소' 사용
    # 주소 뒤에 ID를 붙이지 않는 것이 플로우 관리자 API의 핵심 규격입니다.
    attempts = [
        # 1. 게시글 작성 (OperationID: createPost)
        ("https://api.flow.team/v1/posts", {"project_code": p_id, "title": "🤖 챗봇 민원 접수", "body": content}),
        # 2. 채팅 메시지 전송 (OperationID: createChatMessage)
        ("https://api.flow.team/v1/messages", {"room_code": p_id, "content": content})
    ]

    last_error = ""
    for url, payload in attempts:
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=5)
            if res.status_code == 200:
                return True, "전송 성공"
            last_error = f"{res.status_code}: {res.text}"
        except Exception as e:
            last_error = str(e)
            continue
    return False, last_error

# --------------------------------------------------------------------------
# [3] UI 및 로직 (성함 언급 금지 지침 반영)
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.header("🔒 임직원 신원 확인")
    with st.form("login"):
        name_in = st.text_input("성명")
        pw_in = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
        if st.form_submit_button("접속"):
            if name_in in EMPLOYEE_DB and EMPLOYEE_DB[name_in]["pw"] == pw_in:
                st.session_state["logged_in"], st.session_state["user"] = True, {**EMPLOYEE_DB[name_in], "name": name_in}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")
else:
    user = st.session_state["user"]
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user['rank']}**")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        if user['name'] in ["이경한", "관리자"]:
            st.divider()
            st.markdown("### 🛠️ 관리자 도구")
            
            # 진단 도구 수정 (getProjects 권한이 없을 경우를 대비해 예외처리)
            if st.button("🔍 API 키 진단"):
                headers = {"x-flow-api-key": flow_secrets.get("api_key")}
                res = requests.get("https://api.flow.team/v1/projects", headers=headers)
                if res.status_code == 200: st.json(res.json())
                else: st.error(f"진단 실패({res.status_code}): Rule-Set에 getProjects 권한을 추가해보세요.")

            if st.button("🔔 Flow 연동 테스트"):
                with st.status("플로우 API 전송 시도 중...") as status:
                    success, msg = send_flow_alert("테스트", "시스템 연동 테스트 메시지입니다.", user['name'], user['dept'])
                    if success:
                        status.update(label="✅ 전송 성공!", state="complete")
                        st.sidebar.success("플로우 프로젝트를 확인하세요!")
                    else:
                        status.update(label="❌ 전송 실패", state="error")
                        st.sidebar.error(f"사유: {msg}")

    st.markdown(f"### 👋 안녕하세요, {user['name']}님!")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 무엇을 도와드릴까요?"}]

    for msg in st.session_state.messages: st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # 지침: 매니저님 성함 언급 금지 및 상담 번호 반영
        sys_msg = f"""너는 KCIM의 HR AI 매니저야.
        1. 시설/수리 관련 질문에는 반드시 [ACTION] 태그를 붙여.
        2. 답변 시 절대 '이경한 매니저'라는 성함을 직접 언급하지 마. 
        3. 대신 '해당 사안은 담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
        4. 모든 답변 끝에 [CATEGORY:분류]를 달아줘.
        5. 상담 안내 번호는 반드시 02-772-5806으로 안내해.
        """
        
        try:
            res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
            ans = res.choices[0].message.content
            cat = re.search(r'\[CATEGORY:(.*?)\]', ans).group(1) if "[CATEGORY:" in ans else "기타"
            status = "담당자확인필요" if "[ACTION]" in ans else "처리완료"
            clean_ans = ans.replace("[ACTION]", "").replace(f"[CATEGORY:{cat}]", "").strip()
            
            if status == "담당자확인필요": send_flow_alert(cat, prompt, user['name'], user['dept'])
            st.session_state.messages.append({"role": "assistant", "content": clean_ans})
            st.chat_message("assistant").write(clean_ans)
        except Exception as e: st.error(f"오류: {e}")
