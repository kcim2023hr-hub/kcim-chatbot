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
# [1] 데이터 로드 로직
# --------------------------------------------------------------------------

# 1-1. 직원 명단 로드
@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    # 기본 관리자 계정 설정
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
                    # 휴대폰 뒷 4자리를 초기 비밀번호로 설정
                    pw = phone_digits[-4:] if len(phone_digits) >= 4 else "0000"
                    db[name] = {"pw": pw, "dept": dept, "rank": rank}
                except: continue
            # 특정 사용자 예외 처리
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except Exception as e: st.error(f"❌ 엑셀 파일 읽기 실패: {e}")
    return db

EMPLOYEE_DB = load_employee_db()

# 1-2. 사내 지식 데이터 로드 (PDF, TXT)
@st.cache_data
def load_data():
    org_text, general_rules, intranet_guide = "", "", ""
    for file_name in os.listdir('.'):
        # 조직도 데이터
        if "org" in file_name.lower() or "조직도" in file_name.lower():
            try:
                with open(file_name, 'r', encoding='utf-8') as f: org_text += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: org_text += f.read() + "\n"
        # 인트라넷 가이드
        elif "intranet" in file_name.lower() and file_name.endswith('.txt'):
            try:
                with open(file_name, 'r', encoding='utf-8') as f: intranet_guide += f.read() + "\n"
            except:
                with open(file_name, 'r', encoding='cp949') as f: intranet_guide += f.read() + "\n"
        # 사내 규정 PDF
        elif file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(file_name)
                content = "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])
                general_rules += f"\n\n=== [사내 규정: {file_name}] ===\n{content}\n"
            except: pass
        # 기타 참고 TXT
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                with open(file_name, 'r', encoding='utf-8') as f: content = f.read()
            except:
                with open(file_name, 'r', encoding='cp949') as f: content = f.read()
            general_rules += f"\n\n=== [참고 자료: {file_name}] ===\n{content}\n"
    return org_text, general_rules, intranet_guide

ORG_CHART_DATA, COMPANY_RULES, INTRANET_GUIDE = load_data()

# 업무 분장표 데이터 (2026-01-02 지침 반영)
WORK_DISTRIBUTION = """
[경영관리본부 업무 분장표]
- 이경한: 사옥/법인차량 관리, 현장 숙소 관리, 근태/연차/휴가 관리, 행사 기획/실행, 제증명 발급, 지출결의(출장/숙소), 간식구매 등
- 김병찬: 제도 공지, 위임전결, 취업규칙, 평가보상, 계약서 검토
- 백다영: 교육(리더/법정), 채용, 입퇴사 안내, 양식 변경
- 김승민: 품의서 관리, 세금계산서, 법인카드 비용처리, 숙소 월세/관리비 지출결의
- 안하련: 급여 서류(원천징수), 품의 금액 송금
- 손경숙: 비품 구매
- 최관식: 내부 직원 정보 관리 (어울지기, 플로우)
"""

# --------------------------------------------------------------------------
# [2] 외부 서비스 설정 (OpenAI & Google Sheets)
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"설정 오류: {e}")
    st.stop()

def save_to_sheet(dept, name, rank, category, question, answer, status):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status]) 
    except: pass

def summarize_text(text):
    if len(text) < 30: return text
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "system", "content": "1~2문장으로 요약해줘."}, {"role": "user", "content": text}], 
            temperature=0
        )
        return completion.choices[0].message.content.strip()
    except: return text[:100] + "..."

def check_finish_intent(user_input):
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "system", "content": "종료 의도면 'FINISH', 아니면 'CONTINUE'"}, {"role": "user", "content": user_input}], 
            temperature=0
        )
        return completion.choices[0].message.content.strip()
    except: return "CONTINUE"

# --------------------------------------------------------------------------
# [3] UI 및 로직 실행
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

# [로그인 화면]
if not st.session_state["logged_in"]:
    st.header("🔒 임직원 접속 (신원확인)")
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        input_name = col1.text_input("성명")
        input_pw = col2.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
        
        # --- 수정된 안내 문구 ---
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")

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
                st.error("성명 또는 비밀번호가 일치하지 않습니다.")

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user['rank']}**\n🏢 **{user['dept']}**")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        if user['name'] in ["이경한", "관리자"]:
            with st.expander("🛠️ 관리자 도구"):
                st.write("✅ 데이터 로드 완료")
                st.write(f"- 조직도/규정/가이드 활성화됨")

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "반갑습니다! 👋 **복지, 규정, 시설 이용** 등 궁금한 점을 물어보세요."}]
    
    if "awaiting_confirmation" not in st.session_state: st.session_state["awaiting_confirmation"] = False

    # 대화 기록 표시
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    # 채팅 입력
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # 종료 확인 단계인 경우
        if st.session_state["awaiting_confirmation"]:
            if check_finish_intent(prompt) == "FINISH":
                st.chat_message("assistant").write("늘 좋은 하루 보내세요😊")
                st.session_state["awaiting_confirmation"] = False
                st.stop()
            else:
                st.session_state["awaiting_confirmation"] = False

        # 일반 답변 생성 단계
        if not st.session_state["awaiting_confirmation"]:
            system_instruction = f"""
            너는 1990년 창립된 건설 IT 선도 기업 KCIM의 HR/총무 AI 매니저야.
            친절하고 전문적인 태도로 임직원의 문의에 답변해줘.

            [사내 데이터]
            {ORG_CHART_DATA}
            {COMPANY_RULES}
            {INTRANET_GUIDE}
            {WORK_DISTRIBUTION}

            [원칙]
            1. 대표 안내 번호: 02-772-5806 고정.
            2. 담당자 지칭: 반드시 '성함 + 매니저'라고 정중히 표현해 (예: 이경한 매니저).
            3. 시설/수리/숙소/차량 관련: "HR팀 이경한 매니저에게 문의바랍니다."라고 안내하고 [ACTION] 태그를 포함해.
            4. 답변 끝에 반드시 [CATEGORY:분류명] 태그를 추가해 (예: [CATEGORY:복리후생]).
            """
            
            try:
                completion = client.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                )
                raw_response = completion.choices[0].message.content
            except:
                raw_response = "죄송합니다. 시스템 오류로 답변을 드릴 수 없습니다. 잠시 후 다시 시도해주세요."

            # 태그 추출 및 데이터 정제
            category = re.search(r'\[CATEGORY:(.*?)\]', raw_response).group(1) if "[CATEGORY:" in raw_response else "기타"
            final_status = "담당자확인필요" if "[ACTION]" in raw_response else "처리완료"
            clean_ans = raw_response.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
            
            # 구글 시트 로그 기록
            save_to_sheet(user['dept'], user['name'], user['rank'], category, summarize_text(prompt), summarize_text(clean_ans), final_status)

            # 최종 응답 표시
            full_response = clean_ans + "\n\n**더 이상의 민원은 없으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.chat_message("assistant").write(full_response)
            st.session_state["awaiting_confirmation"] = True
