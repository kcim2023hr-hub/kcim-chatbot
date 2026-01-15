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
# [1] 데이터 로드 (02-772-5806 업데이트 완료)
# --------------------------------------------------------------------------

@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    # 전화번호 수정 반영
    db["관리자"] = {"pw": "1323", "dept": "HR팀", "rank": "매니저", "tel": "02-772-5806"}
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
# [2] 외부 연동 설정
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
    flow_secrets = st.secrets.get("flow", None)
except Exception as e:
    st.error(f"🔑 설정 오류: {e}")
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

# ★ [수정] 404 방지를 위해 Post API와 Message API를 통합 시도
def send_flow_alert(category, question, name, dept):
    if not flow_secrets: return
    api_key = flow_secrets.get("api_key")
    room_code = flow_secrets.get("flow_room_code", "")
    
    if not room_code: return

    headers = {"Content-Type": "application/json", "x-flow-api-key": api_key}
    content = f"[🚨 챗봇 민원 알림]\n- 요청자: {name} ({dept})\n- 분류: {category}\n- 내용: {question}"

    # 프로젝트 게시글로 시도 (가장 권장되는 방식)
    try:
        url = "https://api.flow.team/v1/projects/posts"
        payload = {"project_code": room_code, "title": "🤖 챗봇 민원 접수", "body": content}
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            st.toast("✅ Flow 알림 성공")
            return
    except: pass

    # 게시글 실패 시 메시지로 재시도
    try:
        url = "https://api.flow.team/v1/messages/room"
        payload = {"room_code": room_code, "content": content}
        requests.post(url, json=payload, headers=headers, timeout=5)
    except: pass

# --------------------------------------------------------------------------
# [3] UI 및 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.header("🔒 임직원 신원 확인")
    with st.form("login"):
        name_input = st.text_input("성명")
        pw_input = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속"):
            if name_input in EMPLOYEE_DB and EMPLOYEE_DB[name_input]["pw"] == pw_input:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = EMPLOYEE_DB[name_input]
                st.session_state["user_info"]["name"] = name_input
                st.rerun()
            else: st.error("정보 불일치")
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user.get('rank','')}**")
        st.caption(f"🏢 {user.get('dept','')}")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        
        if user['name'] in ["이경한", "관리자"]:
            st.divider()
            st.markdown("### 🛠️ 관리자 도구")
            # ★ 진짜 방 번호를 찾아주는 도구 추가
            if st.button("🚀 플로우 방 번호(SRNO) 조회"):
                try:
                    res = requests.get("https://api.flow.team/v1/projects", headers={"x-flow-api-key": flow_secrets["api_key"]})
                    if res.status_code == 200:
                        data = res.json().get("list", [])
                        st.write("아래에서 방 번호를 찾아 Secrets에 넣어주세요:")
                        for p in data:
                            st.code(f"방이름: {p.get('TITLE')} -> 번호: {p.get('PROJECT_SRNO')}")
                    else: st.error("조회 실패 (API 키 확인 필요)")
                except Exception as e: st.error(f"오류: {e}")

            with st.expander("📂 파일 현황"):
                for f in os.listdir('.'):
                    if f.endswith(('.pdf', '.txt')) and f != 'requirements.txt': st.caption(f"- {f}")

    st.markdown(f"### 👋 안녕하세요, {user['name']} 매니저님!")
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 궁금한 점이 있으시면 언제든 물어보세요."}]

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        system_instruction = f"""너는 KCIM의 HR/총무 매니저야.
        [자료]: {ORG_CHART_DATA} {COMPANY_RULES} {INTRANET_GUIDE}
        
        1. 시설/수리 관련 질문은 [ACTION] 태그를 붙여. (특정 매니저 언급 문구는 제외)
        2. 모든 답변 끝에 [CATEGORY:분류]를 달아줘.
        3. 전화번호 안내가 필요하면 02-772-5806으로 안내해.
        """
        
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
            )
            raw = completion.choices[0].message.content
            
            category = "기타"
            cat_match = re.search(r'\[CATEGORY:(.*?)\]', raw)
            if cat_match: category = cat_match.group(1)
            
            final_status = "담당자확인필요" if "[ACTION]" in raw else "처리완료"
            clean_ans = raw.replace("[ACTION]","").replace(f"[CATEGORY:{category}]","").strip()
            
            save_to_sheet(user['dept'], user['name'], user.get('rank',''), category, prompt, clean_ans, final_status)
            if final_status == "담당자확인필요":
                send_flow_alert(category, prompt, user['name'], user['dept'])

            st.session_state.messages.append({"role": "assistant", "content": clean_ans})
            st.chat_message("assistant").write(clean_ans)
        except Exception as e: st.error(f"오류: {e}")
