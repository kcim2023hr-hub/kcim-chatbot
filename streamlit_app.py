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
    
    # 비상용 관리자 계정
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
                    
                    # 일반 직원은 휴대폰 뒷 4자리
                    pw = phone_digits[-4:] if len(phone_digits) >= 4 else "0000"
                    
                    db[name] = {"pw": pw, "dept": dept, "rank": rank}
                except:
                    continue
            
            # ★ [중요] 이경한 매니저님 비밀번호 강제 변경 (휴대폰 번호 무시)
            if "이경한" in db:
                db["이경한"]["pw"] = "1323"

        except Exception as e:
            st.error(f"❌ 엑셀 파일 읽기 실패: {e}")
            
    return db

EMPLOYEE_DB = load_employee_db()

# 1-2. 데이터 로드 (조직도 vs 일반규정 분리)
@st.cache_data
def load_data():
    org_text = ""
    general_rules = ""
    
    for file_name in os.listdir('.'):
        # 1. 조직도 파일(org_chart.txt)
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            if file_name.endswith('.txt'):
                try:
                    with open(file_name, 'r', encoding='utf-8') as f:
                        org_text += f.read() + "\n"
                except:
                    with open(file_name, 'r', encoding='cp949') as f:
                        org_text += f.read() + "\n"
            continue 

        # 2. PDF 규정
        if file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                content = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted: content += extracted + "\n"
                general_rules += f"\n\n=== [사내 규정 파일: {file_name}] ===\n{content}\n"
            except: pass
        
        # 3. TXT 자료 (업무분장표 등)
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                with open(file_name, 'r', encoding='utf-8') as f: content = f.read()
            except:
                with open(file_name, 'r', encoding='cp949') as f: content = f.read()
            general_rules += f"\n\n=== [참고 자료: {file_name}] ===\n{content}\n"

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
        pass

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
    
    # ----------------------------------------------------------------------
    # [사이드바] 사용자 정보 및 관리자용 메뉴
    # ----------------------------------------------------------------------
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user['rank']}**")
        st.markdown(f"🏢 **{user['dept']}**")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        
        # 관리자 전용 기능 (이경한, 관리자)
        if user['name'] in ["이경한", "관리자"]:
            st.divider()
            st.markdown("### 🛠️ 관리자 도구")
            
            # 1. 파일 트리 보기
            with st.expander("📂 시스템 파일 현황", expanded=False):
                all_files = sorted(os.listdir('.'))
                pdfs = [f for f in all_files if f.lower().endswith('.pdf')]
                txts = [f for f in all_files if f.lower().endswith('.txt') and f != 'requirements.txt']
                excels = [f for f in all_files if f.lower().endswith(('.xlsx', '.csv'))]
                
                if pdfs:
                    st.markdown("**📄 규정 문서 (PDF)**")
                    for f in pdfs: st.caption(f"- {f}")
                if txts:
                    st.markdown("**📝 텍스트 데이터 (TXT)**")
                    for f in txts: st.caption(f"- {f}")
                if excels:
                    st.markdown("**📊 엑셀 데이터 (XLSX/CSV)**")
                    for f in excels: st.caption(f"- {f}")

            # 2. 데이터 읽기 상태 확인
            with st.expander("👀 데이터 로드 상태 확인", expanded=False):
                st.write("✅ [1] 조직도 데이터 (앞부분)")
                st.text(ORG_CHART_DATA[:150] + "...")
                st.write("✅ [2] 규정/업무분장 (앞부분)")
                st.text(COMPANY_RULES[:150] + "...")

    # ----------------------------------------------------------------------
    # [메인 화면] 챗봇 인터페이스
    # ----------------------------------------------------------------------
    st.markdown(f"### 👋 안녕하세요, {user['name']} {user['rank']}님!")

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "반갑습니다! 👋 **복지, 규정, 조직도, 시설 이용** 등 궁금한 점이 있으시면 언제든 물어보세요."}]
    
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
            너는 KCIM의 HR/총무 AI 매니저야. 아래 [사고 과정]을 순서대로 거쳐서 답변해.

            [1단계: 질문자 파악]
            - 질문자: {user['name']} ({user['dept']} {user['rank']})
            
            [2단계: 사내 데이터 우선 검색]
            {ORG_CHART_DATA}
            {COMPANY_RULES}

            [3단계: 답변 작성 원칙 (매우 중요!)]
            
            ★ 0순위 (시설 관련 문의) ★
            - 질문에 '시설', '사옥', '주차', '청소', '건물', '수리', '에어컨', '난방' 등의 키워드가 포함되거나 시설 관련 불만/요청이라면,
            - 다른 내용을 찾지 말고 무조건 "시설 관련 문의는 **HR팀 이경한 매니저에게 문의바랍니다.**"라고만 답해.
            - 그리고 [ACTION] 태그를 붙여.

            1. (사내 자료에 답이 있는 경우): 무조건 사내 자료를 기준으로 답변해.
            
            2. (사내 자료에 없지만, 일반적인 법률/지식인 경우):
               - 네가 학습한 일반 지식(근로기준법, 세법 등)을 활용해서 답변해.
               - 단, 답변 시작 전에 반드시 "⚠️ 이 내용은 사내 규정집에는 없으며, 일반적인 기준에 따른 안내입니다." 라는 경고 문구를 붙여.
            
            3. (사내 자료에도 없고, 일반 지식도 아닌 '회사 고유 정보'인 경우):
               - 절대 지어내지 말고, 업무분장표를 보고 담당자를 찾아 연결해줘.
               - "이 부분은 규정집에 없어 확인이 필요합니다. OOO 담당자님께 문의해주세요."라고 하고 [ACTION] 태그를 붙여.
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
