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

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드
# --------------------------------------------------------------------------

# 1-1. 직원 명단 로드
@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    db["관리자"] = {"pw": "1234", "dept": "HR팀", "rank": "매니저"}

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
                except:
                    continue
        except Exception as e:
            st.error(f"❌ 엑셀 파일 읽기 실패: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

# 1-2. 사내 규정 로드 (가이드라인 + 모든 파일)
@st.cache_data
def load_rules():
    combined_rules = ""
    guide_content = "" # 가이드라인 내용은 맨 앞으로 빼기 위해 따로 저장
    
    for file_name in os.listdir('.'):
        
        # (1) PDF 파일 읽기
        if file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                combined_rules += f"\n\n--- [규정 파일: {file_name}] ---\n{text}"
            except Exception as e:
                print(f"PDF 오류: {file_name}")

        # (2) TXT 파일 읽기
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                try:
                    with open(file_name, 'r', encoding='utf-8') as f:
                        text = f.read()
                except:
                    with open(file_name, 'r', encoding='cp949') as f:
                        text = f.read()
                
                # guide.txt는 특별 대우
                if "guide" in file_name.lower():
                    guide_content += f"\n\n[★ 필독 가이드라인: {file_name}]\n{text}\n"
                else:
                    combined_rules += f"\n\n--- [참고 자료: {file_name}] ---\n{text}"
            except Exception as e:
                print(f"TXT 오류: {file_name}")

    # 가이드라인을 최상단에 배치하여 AI가 먼저 읽게 함
    final_content = guide_content + combined_rules
    
    if not final_content:
        return "등록된 규정 파일이 없습니다."
    else:
        return final_content

COMPANY_RULES = load_rules()

# --------------------------------------------------------------------------
# [2] 구글 시트 및 OpenAI 설정
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

def save_to_sheet(dept, name, rank, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, dept, name, rank, question, answer, status]) 
    except Exception as e:
        st.error(f"구글 시트 기록 실패: {e}")

def check_finish_intent(user_input):
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "사용자가 '네, 없습니다', '종료', '끝', '수고하세요' 등 대화를 끝내는 말이거나, 단순한 인사면 'FINISH'. 질문이 이어지면 'CONTINUE'로 답해."},
                {"role": "user", "content": user_input}
            ],
            temperature=0
        )
        return completion.choices[0].message.content.strip()
    except:
        return "CONTINUE"

# --------------------------------------------------------------------------
# [3] 메인 로직
# --------------------------------------------------------------------------
def login():
    st.header("🔒 임직원 접속 (신원확인)")
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
            else:
                st.error("정보가 일치하지 않습니다.")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
else:
    user = st.session_state["user_info"]
    st.markdown(f"👤 **{user['dept']} | {user['name']} {user['rank']}**님")
    if st.button("로그아웃"):
        st.session_state.clear()
        st.rerun()
    st.divider()

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "반갑습니다. KCIM HR/총무 민원 챗봇입니다. 무엇을 도와드릴까요?"}]
    
    if "awaiting_confirmation" not in st.session_state:
        st.session_state["awaiting_confirmation"] = False

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # [CASE 1] 종료 확인
        if st.session_state["awaiting_confirmation"]:
            intent = check_finish_intent(prompt)
            if intent == "FINISH":
                end_msg = "늘 좋은 하루 보내세요😊"
                st.session_state.messages.append({"role": "assistant", "content": end_msg})
                st.chat_message("assistant").write(end_msg)
                st.session_state["awaiting_confirmation"] = False
                st.stop() 
            else:
                st.session_state["awaiting_confirmation"] = False

        # [CASE 2] 질문 처리 (가이드라인 우선 적용)
        if not st.session_state["awaiting_confirmation"]:
            system_instruction = f"""
            너는 KCIM의 HR/총무 AI 매니저야.
            임직원의 질문에 대해 아래 [제공된 사내 자료]를 바탕으로 명확하게 답변해줘.
            
            [제공된 사내 자료]
            {COMPANY_RULES}
            
            [답변 규칙]
            1. '필독 가이드라인'을 먼저 참고하여 사용자의 질문 키워드와 관련된 파일 내용을 찾아 답변해.
            2. 자료에 없는 내용이거나, 현장 조치가 필요한 질문은 [ACTION] 태그를 붙여.
            3. 자료로 설명 가능한 질문은 [INFO] 태그를 붙여.
            """
            
            try:
                completion = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                )
                raw_response = completion.choices[0].message.content
            except Exception as e:
                raw_response = "[INFO] 시스템 오류가 발생했습니다."

            if "[ACTION]" in raw_response:
                final_status = "담당자확인필요"
                clean_response = raw_response.replace("[ACTION]", "").strip()
            else:
                final_status = "처리완료"
                clean_response = raw_response.replace("[INFO]", "").strip()

            save_to_sheet(user['dept'], user['name'], user['rank'], prompt, clean_response, final_status)

            full_response = clean_response + "\n\n**더 이상의 민원은 없으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.chat_message("assistant").write(full_response)
            st.session_state["awaiting_confirmation"] = True
