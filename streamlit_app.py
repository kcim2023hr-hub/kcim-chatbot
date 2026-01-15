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
# [1] 데이터 로드 (02-772-5806 반영 완료)
# --------------------------------------------------------------------------

@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
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
# [2] 외부 연동 (Secrets 기반)
# --------------------------------------------------------------------------
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
        sheet = gs_client.open_by_url("https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit").worksheet("응답시트")
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status]) 
    except: pass

def send_flow_alert(category, question, name, dept):
    if not flow_secrets: return
    api_key = flow_secrets.get("api_key")
    # image_6cbc4f에서 확인된 진짜 프로젝트 ID 적용
    room_code = flow_secrets.get("flow_room_code", "2786111")
    
    headers = {"Content-Type": "application/json", "x-flow-api-key": api_key}
    content = f"[🚨 챗봇 민원 알림]\n- 요청자: {name} ({dept})\n- 분류: {category}\n- 내용: {question}"

    # --- 1순위: 피드(Feed) 게시글 등록 시도 ---
    try:
        url = "https://api.flow.team/v1/projects/posts"
        # 데이터 형식을 content로 변경하여 재시도
        payload = {"project_code": room_code, "title": "🤖 챗봇 민원 접수", "content": content}
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            st.toast("✅ Flow 피드 알림 성공!")
            return
        else:
            # 실패 시 에러 로그를 화면에 출력 (매니저님 확인용)
            st.error(f"❌ 피드 전송 실패 ({res.status_code}): {res.text}")
    except Exception as e:
        st.error(f"❌ 피드 연결 에러: {e}")

    # --- 2순위: 채팅(Chat) 메시지 전송 시도 ---
    try:
        url = "https://api.flow.team/v1/messages/room"
        payload = {"room_code": room_code, "content": content}
        res_msg = requests.post(url, json=payload, headers=headers, timeout=5)
        if res_msg.status_code == 200:
            st.toast("✅ Flow 채팅 알림 성공!")
        else:
            st.error(f"❌ 채팅 전송 실패 ({res_msg.status_code}): {res_msg.text}")
    except Exception as e:
        st.error(f"❌ 채팅 연결 에러: {e}")

# --------------------------------------------------------------------------
# [3] 메인 화면 및 로그인
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
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        
        if user['name'] in ["이경한", "관리자"]:
            st.divider()
            st.markdown("### 🛠️ 관리자 도구")
            with st.expander("📂 파일 현황"):
                for f in os.listdir('.'):
                    if f.endswith(('.pdf', '.txt')) and f != 'requirements.txt': st.caption(f"- {f}")

    st.markdown(f"### 👋 안녕하세요, {user['name']} {user.get('rank','')}님!")
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "반갑습니다! 👋 무엇을 도와드릴까요?"}]

    for msg in st.session_state.messages: st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        system_instruction = f"""너는 KCIM의 HR AI 매니저야. 아래 자료를 바탕으로 답해줘.
        [자료]: {ORG_CHART_DATA} {COMPANY_RULES} {INTRANET_GUIDE}
        
        1. 시설/수리 관련 질문이나 전문적인 답변이 필요한 사안은 반드시 [ACTION] 태그를 붙여.
        2. 절대 '이 문제는 HR팀 이경한 매니저에게 문의하셔야 처리할 수 있습니다'라는 문구는 쓰지 마.
        3. 대신 '해당 사안은 담당 부서의 확인이 필요합니다. 내용을 전달하였으니 잠시만 기다려 주세요.'라고 정중히 답해.
        4. 모든 답변 끝에 [CATEGORY:분류명]을 꼭 달아줘.
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
            if final_status == "담당자확인필요":
                send_flow_alert(category, prompt, user['name'], user['dept'])

            st.session_state.messages.append({"role": "assistant", "content": clean_ans})
            st.chat_message("assistant").write(clean_ans)
        except Exception as e: st.error(f"❌ 오류 발생: {e}")
