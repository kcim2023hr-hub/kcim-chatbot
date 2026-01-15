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
# [1] 데이터 로드 (조직도, 규정, 인트라넷 가이드)
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
    org_text, general_rules, intranet_guide = "", "", ""
    for file_name in os.listdir('.'):
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            try:
                with open(file_name, 'r', encoding='utf-8') as f: org_text += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: org_text += f.read() + "\n"
        elif "intranet" in file_name.lower() and file_name.endswith('.txt'):
            try:
                with open(file_name, 'r', encoding='utf-8') as f: intranet_guide += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: intranet_guide += f.read() + "\n"
        elif file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted: general_rules += extracted + "\n"
            except: pass
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                with open(file_name, 'r', encoding='utf-8') as f: general_rules += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: general_rules += f.read() + "\n"
    return org_text, general_rules, intranet_guide

ORG_CHART_DATA, COMPANY_RULES, INTRANET_GUIDE = load_data()

# --------------------------------------------------------------------------
# [2] 외부 연동 (OpenAI, Google Sheets, Flow API)
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
    flow_secrets = st.secrets.get("flow", None)
except Exception as e:
    st.error(f"🔑 설정 오류: Secrets 설정을 확인해주세요. ({e})")
    st.stop()

def save_to_sheet(dept, name, rank, category, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, dept, name, rank, category, question, answer, status]) 
    except: pass

# ★ [수정됨] 404 에러 방지를 위해 여러 경로로 시도하는 스마트 알림 함수
def send_flow_alert(category, question, name, dept):
    if not flow_secrets: return
    
    # Secrets에서 안전하게 값 가져오기 (없으면 에러 방지)
    api_key = flow_secrets.get("api_key")
    room_code = flow_secrets.get("flow_room_code", "BFLOW_211214145658") # BFLOW 번호 고정
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": api_key}
    icon = "🚨" if "시설" in category else "📢"
    text_content = f"[{icon} 챗봇 민원 알림]\n- 분류: {category}\n- 요청자: {name} ({dept})\n- 내용: {question}"
    payload = {"room_code": room_code, "content": text_content}

    # 404 방지를 위해 가장 유력한 두 가지 주소로 순차 시도
    endpoints = [
        "https://api.flow.team/v1/messages/room",
        "https://api.flow.team/v1/messages/project"
    ]

    success = False
    for url in endpoints:
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            if response.status_code == 200:
                st.toast(f"✅ Flow 알림 전송 성공! ({url.split('/')[-1]})")
                success = True
                break
        except: continue

    if not success:
        st.error(f"❌ Flow 알림 실패: 모든 경로(404)를 확인했지만 방을 찾을 수 없습니다. [코드: {room_code}]")

# --------------------------------------------------------------------------
# [3] 메인 화면 및 로그인
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.header("🔒 임직원 신원 확인")
    with st.form("login"):
        name = st.text_input("성명")
        pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
        if st.form_submit_button("접속"):
            if name in EMPLOYEE_DB and EMPLOYEE_DB[name]["pw"] == pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = EMPLOYEE_DB[name]
                st.session_state["user_info"]["name"] = name
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user.get('rank','')}**")
        st.caption(f"🏢 {user.get('dept','')}")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()

    st.markdown(f"### 👋 안녕하세요, {user['name']}님!")
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 무엇을 도와드릴까요?"}]

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        system_instruction = f"""너는 KCIM의 HR/총무 매니저야. 아래 자료를 바탕으로 친절하게 답해줘.
        [조직도]: {ORG_CHART_DATA} [규정]: {COMPANY_RULES} [인트라넷 가이드]: {INTRANET_GUIDE}
        
        1. 시설/수리 관련 질문은 반드시 "HR팀 이경한 매니저에게 문의바랍니다."라고 답하고 끝에 [CATEGORY:시설/환경] [ACTION] 태그를 붙여.
        2. 인트라넷 메뉴 위치 질문은 가이드를 참고해 정확한 경로(>)를 안내해.
        3. 모든 답변 끝에는 [CATEGORY:분류명]을 꼭 달아줘.
        """
        
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
            )
            response_text = completion.choices[0].message.content
            
            category = "기타"
            cat_match = re.search(r'\[CATEGORY:(.*?)\]', response_text)
            if cat_match: category = cat_match.group(1)
            
            final_status = "담당자확인필요" if "[ACTION]" in response_text else "처리완료"
            clean_ans = response_text.replace("[ACTION]","").replace(f"[CATEGORY:{category}]","").strip()
            
            save_to_sheet(user['dept'], user['name'], user.get('rank',''), category, prompt, clean_ans, final_status)
            if final_status == "담당자확인필요":
                send_flow_alert(category, prompt, user['name'], user['dept'])

            st.session_state.messages.append({"role": "assistant", "content": clean_ans})
            st.chat_message("assistant").write(clean_ans)
        except Exception as e:
            st.error(f"❌ 챗봇 응답 중 오류 발생: {e}")
