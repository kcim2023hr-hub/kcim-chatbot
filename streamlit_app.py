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
import json

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드 (02-772-5806 반영 및 Syntax Error 수정)
# --------------------------------------------------------------------------

@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    # 전화번호 수정: 02-772-5806
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
        # [SyntaxError 수정] try와 with 문을 별도 라인으로 분리
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    org_text += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f:
                    org_text += f.read() + "\n"
        elif "intranet" in file_name.lower() and file_name.endswith('.txt'):
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    intranet_guide += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f:
                    intranet_guide += f.read() + "\n"
        elif file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted: general_rules += extracted + "\n"
            except: pass
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    general_rules += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f:
                    general_rules += f.read() + "\n"
    return org_text, general_rules, intranet_guide

ORG_CHART_DATA, COMPANY_RULES, INTRANET_GUIDE = load_data()

# --------------------------------------------------------------------------
# [2] 외부 연동 (Secrets 기반)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
    flow_secrets = st.secrets.get("flow", None)
except Exception as e:
    st.error(f"🔑 설정 오류: Secrets를 확인하세요. ({e})")
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
    if not flow_secrets: return
    api_key = flow_secrets.get("api_key")
    room_code = flow_secrets.get("flow_room_code")
    if not room_code: return

    headers = {"Content-Type": "application/json", "x-flow-api-key": api_key}
    content = f"[🚨 챗봇 민원 알림]\n- 요청자: {name} ({dept})\n- 분류: {category}\n- 내용: {question}"

    # 프로젝트 게시글(Post) 생성 시도
    try:
        url = "https://api.flow.team/v1/projects/posts"
        payload = {"project_code": room_code, "title": "🤖 챗봇 민원 접수", "body": content}
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            st.toast("✅ Flow 알림 성공")
            return
    except: pass

    # 게시글 실패 시 메시지 전송 시도
    try:
        url = "https://api.flow.team/v1/messages/room"
        requests.post(url, json={"room_code": room_code, "content": content}, headers=headers, timeout=5)
    except: pass

# --------------------------------------------------------------------------
# [3] UI 및 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "show_debug" not in st.session_state: st.session_state["show_debug"] = False

if not st.session_state["logged_in"]:
    st.header("🔒 임직원 신원 확인")
    with st.form("login"):
        name_input = st.text_input("성명")
        pw_input = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
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
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        
        if user['name'] in ["이경한", "관리자"]:
            st.divider()
            st.markdown("### 🛠️ 관리자 도구")
            if st.button("🚀 플로우 방 번호(SRNO) 조회"):
                st.session_state["show_debug"] = True

            with st.expander("📂 시스템 파일 현황"):
                for f in os.listdir('.'):
                    if f.endswith(('.pdf', '.txt')) and f != 'requirements.txt': st.caption(f"- {f}")

    # --- 방 번호 조회 결과 출력 (메인 화면) ---
    if st.session_state.get("show_debug"):
        st.info("🔍 플로우 프로젝트 목록 분석 중...")
        try:
            res = requests.get("https://api.flow.team/v1/projects", headers={"x-flow-api-key": flow_secrets["api_key"]})
            data = res.json()
            # image_6c5b0b.png의 구조에 맞게 리스트 추출
            project_list = data.get("response", {}).get("data", {}).get("projects", {}).get("projects", [])
            
            if project_list:
                st.write("아래 리스트에서 **[민원챗봇] 수신전용프로젝트**를 찾아 ID 숫자를 Secrets에 입력하세요.")
                for p in project_list:
                    # SRNO 또는 고유 ID 필드 확인 (일반적으로 project_srno)
                    p_name = p.get("project_title", p.get("TITLE", "이름없음"))
                    p_id = p.get("project_srno", p.get("PROJECT_SRNO", "ID없음"))
                    st.code(f"방이름: {p_name}  👉  ID: {p_id}")
            else:
                st.warning("조회된 프로젝트가 없습니다. 권한 설정을 확인하세요.")
                st.json(data) # 원본 데이터 확인용
        except Exception as e: st.error(f"오류: {e}")
        if st.button("닫기"): 
            st.session_state["show_debug"] = False
            st.rerun()

    st.markdown(f"### 👋 안녕하세요, {user['name']} {user.get('rank','')}님!")
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 **복지, 규정, 불편사항, 시설 이용** 등 궁금한 점을 물어보세요."}]

    for msg in st.session_state.messages: st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # 요청사항: 특정 문구 제거 및 전문적 안내
        system_instruction = f"""너는 KCIM의 HR AI 매니저야.
        [자료]: {ORG_CHART_DATA} {COMPANY_RULES} {INTRANET_GUIDE}
        
        1. 시설/수리 관련 질문이나 직접 해결이 어려운 요청은 [ACTION] 태그를 붙여.
        2. 절대 '이 문제는 HR팀 이경한 매니저에게 문의하셔야 처리할 수 있습니다'라는 문구는 쓰지 마.
        3. 대신 '해당 사안은 담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
        4. 모든 답변 끝에 [CATEGORY:분류]를 달아.
        5. 전화번호 안내가 필요하면 반드시 02-772-5806으로 안내해.
        """
        
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
            )
            raw = completion.choices[0].message.content
            category = re.search(r'\[CATEGORY:(.*?)\]', raw).group(1) if "[CATEGORY:" in raw else "기타"
            final_status = "담당자확인필요" if "[ACTION]" in raw else "처리완료"
            clean_ans = raw.replace("[ACTION]","").replace(f"[CATEGORY:{category}]","").strip()
            
            save_to_sheet(user['dept'], user['name'], user.get('rank',''), category, prompt, clean_ans, final_status)
            if final_status == "담당자확인필요": send_flow_alert(category, prompt, user['name'], user['dept'])
            
            st.session_state.messages.append({"role": "assistant", "content": clean_ans})
            st.chat_message("assistant").write(clean_ans)
        except Exception as e: st.error(f"오류: {e}")
