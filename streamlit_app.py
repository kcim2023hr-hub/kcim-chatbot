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

# 1. 페이지 및 기본 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 및 DB 로드
# --------------------------------------------------------------------------
@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    # 상담 번호: 02-772-5806 고정
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

@st.cache_data
def load_docs():
    org, rules, intranet = "", "", ""
    for f_name in os.listdir('.'):
        try:
            if "org" in f_name.lower() or "조직도" in f_name.lower():
                with open(f_name, 'r', encoding='utf-8') as f: org += f.read() + "\n"
            elif f_name.lower().endswith('.pdf'):
                reader = PyPDF2.PdfReader(f_name)
                for page in reader.pages: rules += (page.extract_text() or "") + "\n"
            elif "intranet" in f_name.lower() and f_name.endswith('.txt'):
                with open(f_name, 'r', encoding='utf-8') as f: intranet += f.read() + "\n"
        except: pass
    return org, rules, intranet

ORG_DATA, RULES_DATA, INTRANET_DATA = load_docs()

# --------------------------------------------------------------------------
# [2] 외부 연동 (Flow 404 에러 정면 돌파 로직)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
    flow_secrets = st.secrets.get("flow", None)
except Exception as e:
    st.error(f"🔑 Secrets 설정 오류: {e}")
    st.stop()

def save_to_sheet(dept, name, rank, category, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url("https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit").worksheet("응답시트")
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status])
    except: pass

def send_flow_alert(category, question, name, dept):
    if not flow_secrets: return False, "Secrets 설정 누락"
    api_key = flow_secrets.get("api_key")
    p_id = "2786111" # 확인된 프로젝트 ID
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": api_key}
    content = f"[🚨 챗봇 민원 알림]\n- 요청자: {name} ({dept})\n- 분류: {category}\n- 내용: {question}"

    # 404 해결: OperationID 'createPost'와 일치하는 표준 경로 시도
    url = f"https://api.flow.team/v1/projects/{p_id}/posts"
    payload = {"title": "🤖 챗봇 민원 접수", "body": content}

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            return True, "전송 성공"
        else:
            # 백업 경로 시도 (메시지 발송)
            msg_url = f"https://api.flow.team/v1/messages/room"
            requests.post(msg_url, json={"room_code": p_id, "content": content}, headers=headers, timeout=5)
            return False, f"{res.status_code}: {res.text}"
    except Exception as e:
        return False, str(e)

# --------------------------------------------------------------------------
# [3] UI 및 로직
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
            if st.button("🔔 Flow 연동 테스트"):
                with st.status("전송 시도 중...") as s:
                    ok, err = send_flow_alert("테스트", "연동 확인용 메시지", user['name'], user['dept'])
                    if ok: s.update(label="✅ 성공!", state="complete")
                    else: st.error(f"실패: {err}")

    st.markdown(f"### 👋 안녕하세요, {user['name']} {user['rank']}님!")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 무엇을 도와드릴까요?"}]

    for msg in st.session_state.messages: st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # 지침 반영: 성함 언급 금지 및 상담 번호 02-772-5806
        sys_msg = f"""너는 KCIM HR AI야. 아래 자료를 참고해.
        [자료]: {ORG_DATA} {RULES_DATA} {INTRANET_DATA}
        1. 시설/수리 질문에는 반드시 [ACTION] 태그를 붙여.
        2. 절대 '이경한 매니저' 성함을 언급하지 마. 
        3. 대신 '담당 부서의 확인이 필요합니다. 내용을 전달했으니 잠시만 기다려 주세요.'라고 답해.
        4. 모든 답변 끝에 [CATEGORY:분류]를 달아.
        5. 상담 번호는 반드시 02-772-5806으로 안내해.
        """
        
        try:
            res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}])
            ans = res.choices[0].message.content
            cat = re.search(r'\[CATEGORY:(.*?)\]', ans).group(1) if "[CATEGORY:" in ans else "기타"
            status = "담당자확인필요" if "[ACTION]" in ans else "처리완료"
            clean_ans = ans.replace("[ACTION]", "").replace(f"[CATEGORY:{cat}]", "").strip()
            
            save_to_sheet(user['dept'], user['name'], user['rank'], cat, prompt, clean_ans, status)
            if status == "담당자확인필요": send_flow_alert(cat, prompt, user['name'], user['dept'])
            
            st.session_state.messages.append({"role": "assistant", "content": clean_ans})
            st.chat_message("assistant").write(clean_ans)
        except Exception as e: st.error(f"오류: {e}")
