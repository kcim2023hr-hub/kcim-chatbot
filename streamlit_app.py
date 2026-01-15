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

# 1-2. 조직도 및 규정 로드 (분리 로딩 방식)
@st.cache_data
def load_data():
    org_text = ""
    general_rules = ""
    
    for file_name in os.listdir('.'):
        # 1. 조직도 파일(org_chart.txt) 우선 확보
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            if file_name.endswith('.txt'):
                try:
                    with open(file_name, 'r', encoding='utf-8') as f:
                        org_text += f.read() + "\n"
                except:
                    with open(file_name, 'r', encoding='cp949') as f:
                        org_text += f.read() + "\n"
            continue # 조직도는 별도로 저장했으니 다음 파일로

        # 2. 나머지 PDF 및 TXT 규정 읽기
        content = ""
        if file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted: content += extracted + "\n"
                general_rules += f"\n\n--- [규정: {file_name}] ---\n{content}"
            except: pass
        
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                with open(file_name, 'r', encoding='utf-8') as f: content = f.read()
            except:
                with open(file_name, 'r', encoding='cp949') as f: content = f.read()
            general_rules += f"\n\n--- [자료: {file_name}] ---\n{content}"

    return org_text, general_rules

ORG_CHART_DATA, COMPANY_RULES = load_data()

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
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "사용자가 '네, 없습니다', '종료', '끝' 등 대화를 끝내는 의도면 'FINISH', 질문이 이어지면 'CONTINUE'로 답해."},
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
    
    # 사이드바 설정
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user['rank']}**")
        st.markdown(f"🏢 **{user['dept']}**")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        
        # ★ 보안 업데이트: 이경한 매니저님과 관리자만 디버그 메뉴를 볼 수 있음
        if user['name'] == "이경한" or user['name'] == "관리자":
            st.divider()
            with st.expander("🛠️ 관리자용 데이터 확인"):
                st.write("▼ 조직도 로드 상태")
                if ORG_CHART_DATA:
                    st.success("조직도(org_chart.txt) 로드 성공")
                    st.text(ORG_CHART_DATA[:200] + "...") 
                else:
                    st.error("조직도 파일이 없습니다!")

    st.markdown(f"### 👋 안녕하세요, {user['name']} {user['rank']}님!")
    st.markdown("무엇을 도와드릴까요?")

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "규정이나 결재 관련 궁금한 점이 있으신가요?"}]
    
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

        # [CASE 2] 답변 생성
        if not st.session_state["awaiting_confirmation"]:
            
            system_instruction = f"""
            너는 KCIM의 HR/총무 AI 매니저야.
            
            [질문자 프로필]
            - 이름: {user['name']}
            - 부서: {user['dept']}
            - 직급: {user['rank']}
            
            [★ 핵심 데이터: 조직도 및 결재권자]
            (아래 내용에서 질문자의 부서를 찾아 결재권자 실명을 반드시 확인해)
            {ORG_CHART_DATA}
            
            [참고 자료: 사내 규정]
            {COMPANY_RULES}
            
            [답변 가이드]
            1. '결재', '승인', '누구한테' 같은 질문이 나오면 무조건 [핵심 데이터: 조직도]를 먼저 봐.
            2. 질문자가 속한 팀/그룹을 찾고, 그 조직의 책임자(팀장/그룹장) 이름을 콕 집어서 답변해.
               (예: "이경한 님은 HR팀이므로 김병찬 팀장님 전결입니다.")
            3. 만약 조직도에 이름이 없다면 규정대로 직책(팀장 등)만 안내해.
            4. 현장 조치가 필요하면 [ACTION], 아니면 [INFO] 태그를 붙여.
            """
            
            try:
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                )
                raw_response = completion.choices[0].message.content
            
            except Exception as e:
                st.error(f"오류: {e}")
                raw_response = "[INFO] 오류가 발생했습니다."

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
