import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
import time
import os
import re
import PyPDF2
import requests

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드
# --------------------------------------------------------------------------

@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    db["관리자"] = {"pw": "1323", "dept": "HR팀", "rank": "매니저"}

    if os.path.exists(file_name):
        try:
            df = pd.read_excel(file_name, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            for _, row in df.iterrows():
                try:
                    name = str(row['이름']).strip()
                    dept = str(row['부서']).strip()
                    rank = str(row['직급']).strip()
                    phone = str(row['휴대폰 번호']).strip()
                    phone_digits = re.sub(r'[^0-9]', '', phone)
                    pw = phone_digits[-4:] if len(phone_digits) >= 4 else "0000"
                    db[name] = {"pw": pw, "dept": dept, "rank": rank}
                except: continue
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except Exception as e: st.error(f"❌ 엑셀 파일 읽기 실패: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

@st.cache_data
def load_data():
    org_text = ""
    general_rules = ""
    intranet_guide = ""
    for file_name in os.listdir('.'):
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            if file_name.endswith('.txt'):
                try: 
                    with open(file_name, 'r', encoding='utf-8') as f: org_text += f.read() + "\n"
                except: 
                    with open(file_name, 'r', encoding='cp949') as f: org_text += f.read() + "\n"
            continue 
        if "intranet" in file_name.lower() and file_name.endswith('.txt'):
            try: 
                with open(file_name, 'r', encoding='utf-8') as f: intranet_guide += f.read() + "\n"
            except: 
                with open(file_name, 'r', encoding='cp949') as f: intranet_guide += f.read() + "\n"
            continue
        if file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                content = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted: content += extracted + "\n"
                general_rules += f"\n\n=== [사내 규정 파일: {file_name}] ===\n{content}\n"
            except: pass
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try: 
                with open(file_name, 'r', encoding='utf-8') as f: content = f.read()
            except: 
                with open(file_name, 'r', encoding='cp949') as f: content = f.read()
            general_rules += f"\n\n=== [참고 자료: {file_name}] ===\n{content}\n"
    return org_text, general_rules, intranet_guide

ORG_CHART_DATA, COMPANY_RULES, INTRANET_GUIDE = load_data()

# --------------------------------------------------------------------------
# [2] 외부 연동 설정
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
    flow_secrets = st.secrets.get("flow", None)
except Exception as e:
    st.error(f"설정 오류: {e}")
    st.stop()

def save_to_sheet(dept, name, rank, category, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, dept, name, rank, category, question, answer, status]) 
    except Exception as e:
        pass

# ★ [수정됨] 디버깅 모드 Flow 알림
def send_flow_alert(category, question, name, dept):
    if not flow_secrets:
        st.error("❌ Flow 설정(Secrets)이 없습니다.")
        return

    try:
        # 1. API URL 확인 (가장 의심되는 부분)
        # Flow 공식 문서상 봇 알림은 보통 이 주소입니다. 안되면 /messages/room 등으로 바꿔야 함.
        url = "https://api.flow.team/v1/messages/user"
        
        api_key = flow_secrets["api_key"]
        target_user = flow_secrets["flow_user_id"]

        icon = "📢"
        if "시설" in category: icon = "🚨"
        
        text_content = f"""[{icon} 챗봇 민원 알림]
- 분류: {category}
- 요청자: {name} ({dept})
- 내용: {question}"""

        headers = {
            "Content-Type": "application/json",
            "x-flow-api-key": api_key
        }
        
        payload = {
            "target_user_id": target_user,
            "content": text_content
        }

        # 전송 및 결과 확인
        st.info(f"📤 Flow 알림 전송 시도 중... (대상: {target_user})")
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        
        if response.status_code == 200:
            st.success("✅ Flow 알림 전송 성공!")
        else:
            # 실패 원인 출력
            st.error(f"❌ 전송 실패! 상태코드: {response.status_code}")
            st.code(response.text) # 에러 메시지 원문 표시
            
    except Exception as e:
        st.error(f"❌ 시스템 에러 발생: {e}")

def summarize_text(text):
    if len(text) < 30: return text
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "핵심만 1~2문장 요약해줘."}, {"role": "user", "content": text}],
            temperature=0
        )
        return completion.choices[0].message.content.strip()
    except: return text[:100] + "..."

def check_finish_intent(user_input):
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "끝내는 의도면 'FINISH', 아니면 'CONTINUE'."}, {"role": "user", "content": user_input}],
            temperature=0
        )
        return completion.choices[0].message.content.strip()
    except: return "CONTINUE"

# --------------------------------------------------------------------------
# [3] 메인 로직
# --------------------------------------------------------------------------
def login():
    st.header("🔒 임직원 접속")
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        input_name = col1.text_input("성명")
        input_pw = col2.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
        if st.form_submit_button("접속하기"):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {
                    "dept": EMPLOYEE_DB[input_name]["dept"],
                    "name": input_name,
                    "rank": EMPLOYEE_DB[input_name]["rank"]
                }
                st.rerun()
            else: st.error("정보 불일치")

if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user['rank']}**")
        st.markdown(f"🏢 **{user['dept']}**")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        if user['name'] in ["이경한", "관리자"]:
            st.divider()
            with st.expander("🛠️ 관리자 도구"):
                st.write("시스템 정상 작동 중")

    st.markdown(f"### 👋 안녕하세요, {user['name']} {user['rank']}님!")

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "반갑습니다! 👋 **복지, 규정, 불편사항, 시설 이용** 등 궁금한 점이 있으시면 언제든 물어보세요."}]
    
    if "awaiting_confirmation" not in st.session_state: st.session_state["awaiting_confirmation"] = False

    for msg in st.session_state.messages: st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        if st.session_state["awaiting_confirmation"]:
            intent = check_finish_intent(prompt)
            if intent == "FINISH":
                end_msg = "늘 좋은 하루 보내세요😊"
                st.session_state.messages.append({"role": "assistant", "content": end_msg})
                st.chat_message("assistant").write(end_msg)
                st.session_state["awaiting_confirmation"] = False
                st.stop() 
            else: st.session_state["awaiting_confirmation"] = False

        if not st.session_state["awaiting_confirmation"]:
            system_instruction = f"""
            너는 KCIM의 HR/총무 AI 매니저야.
            [질문자]: {user['name']} ({user['dept']} {user['rank']})
            [자료]: {ORG_CHART_DATA} {COMPANY_RULES} {INTRANET_GUIDE}
            
            ★ 0순위 (시설 관련 문의) ★
            - 질문이 '시설', '주차', '청소', '건물', '수리', '냉난방' 관련이면:
            - 답변: "시설 관련 문의는 **HR팀 이경한 매니저에게 문의바랍니다.**"
            - 태그: [CATEGORY:시설/환경] [ACTION]

            ★ 1순위 (어울지기/인트라넷) ★
            - 태그: [CATEGORY:프로세스/규정]
            
            2. 일반 답변 시 사내 자료 우선, 없으면 일반 지식(경고문구 포함).
            3. 답변 끝에 태그 필수: [CATEGORY:인사/근태] 등
            """
            
            try:
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                )
                raw_response = completion.choices[0].message.content
            except Exception as e:
                st.error(f"오류: {e}")
                raw_response = "[INFO] 시스템 오류가 발생했습니다."

            category = "기타"
            if "[CATEGORY:" in raw_response:
                match = re.search(r'\[CATEGORY:(.*?)\]', raw_response)
                if match:
                    category = match.group(1)
                    raw_response = raw_response.replace(match.group(0), "")

            if "[ACTION]" in raw_response:
                final_status = "담당자확인필요"
                clean_response = raw_response.replace("[ACTION]", "").strip()
            else:
                final_status = "처리완료"
                clean_response = raw_response.replace("[INFO]", "").strip()

            summary_q = summarize_text(prompt)
            summary_a = summarize_text(clean_response)

            save_to_sheet(user['dept'], user['name'], user['rank'], category, summary_q, summary_a, final_status)

            # ★ 디버깅용 알림 전송 호출
            if final_status == "담당자확인필요":
                send_flow_alert(category, summary_q, user['name'], user['dept'])

            full_response = clean_response + "\n\n**더 이상의 민원은 없으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.chat_message("assistant").write(full_response)
            st.session_state["awaiting_confirmation"] = True
