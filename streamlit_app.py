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
    # 관리자 정보 및 전화번호 업데이트 (02-772-5806)
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

def send_flow_alert(category, question, name, dept):
    if not flow_secrets: return
    api_key = flow_secrets.get("api_key")
    # 매니저님이 찾으신 BFLOW 고유 ID 사용
    room_code = flow_secrets.get("flow_room_code", "BFLOW_211214145658")
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": api_key}
    icon = "🚨" if "시설" in category else "📢"
    
    # 플로우 게시글 형태로 구성
    payload = {
        "project_code": room_code,
        "title": f"[{icon} 챗봇 민원 접수] {name}님",
        "content": f"- 분류: {category}\n- 요청자: {name} ({dept})\n- 내용: {question}\n- 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    }
    
    # 플로우 게시글(Post) 생성 API로 시도
    url = "https://api.flow.team/v1/projects/posts"
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            st.toast("✅ Flow 프로젝트에 민원이 접수되었습니다.")
        else:
            # 실패 시 기존 메시지 방식(Room)으로 백업 시도
            backup_url = "https://api.flow.team/v1/messages/room"
            requests.post(backup_url, json={"room_code": room_code, "content": payload["content"]}, headers=headers, timeout=5)
    except: pass

# --------------------------------------------------------------------------
# [3] 메인 화면 및 로그인
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

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
            else: st.error("정보가 일치하지 않습니다.")
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
            with st.expander("📂 시스템 파일 현황", expanded=False):
                all_files = sorted(os.listdir('.'))
                pdfs = [f for f in all_files if f.lower().endswith('.pdf')]
                txts = [f for f in all_files if f.lower().endswith('.txt') and f != 'requirements.txt']
                if pdfs:
                    st.markdown("**📄 규정 문서 (PDF)**")
                    for f in pdfs: st.caption(f"- {f}")
                if txts:
                    st.markdown("**📝 텍스트 데이터 (TXT)**")
                    for f in txts: st.caption(f"- {f}")
            
            with st.expander("👀 데이터 로드 상태 확인", expanded=False):
                st.write("✅ [1] 조직도 데이터")
                st.text(ORG_CHART_DATA[:50] + "...")
                st.write("✅ [2] 인트라넷 가이드")
                st.text(INTRANET_GUIDE[:50] + "...")

    st.markdown(f"### 👋 안녕하세요, {user['name']} {user.get('rank','')}님!")
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 **복지, 규정, 불편사항, 시설 이용** 등 궁금한 점이 있으시면 언제든 물어보세요."}]

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # 시스템 지침 수정: 특정 문구 제거 및 정확한 전화번호 부여
        system_instruction = f"""너는 KCIM의 HR/총무 매니저야. 아래 자료를 바탕으로 답변해줘.
        [조직도]: {ORG_CHART_DATA} [규정]: {COMPANY_RULES} [인트라넷 가이드]: {INTRANET_GUIDE}
        
        1. 시설/환경/수리 관련 질문이나 답변이 불가능한 전문적인 내용은 [ACTION] 태그를 붙여. 
           (단, "이 문제는 HR팀 이경한 매니저에게 문의하셔야..."라는 문구는 절대 사용하지 마.)
        2. 인트라넷 메뉴 위치 질문은 가이드를 참고해 정확한 경로(>)를 안내해.
        3. 모든 답변 끝에는 [CATEGORY:분류명]을 꼭 달아줘.
        4. 문의 전화번호가 필요하다면 02-772-5806으로 안내해.
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
            st.error(f"❌ 오류 발생: {e}")
