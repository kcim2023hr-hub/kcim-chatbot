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

# --- 커스텀 CSS: 디자인 및 레이아웃 최적화 ---
st.markdown("""
    <style>
    /* 메인 컨테이너 중앙 정렬 및 너비 제한 */
    .block-container {
        max-width: 850px;
        padding-top: 2rem;
    }
    /* 메인 인삿말 타이틀 (크게) */
    .greeting-title {
        font-size: 32px !important;
        font-weight: 800;
        color: #1E1E1E;
        margin-bottom: 8px;
    }
    /* 메인 인삿말 서브타이틀 */
    .greeting-subtitle {
        font-size: 20px !important;
        color: #444;
        margin-bottom: 25px;
    }
    /* 사이드바 접속 정보 - 팀명(부서명) 크게 */
    .sidebar-dept {
        font-size: 19px !important;
        font-weight: 600;
        color: #555;
        margin-top: -10px;
        margin-bottom: 10px;
    }
    /* 사이드바 카테고리 리스트 스타일 */
    .service-item {
        font-size: 15px !important;
        margin-bottom: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드 로직
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
                content = "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])
                general_rules += f"\n\n=== [사내 규정: {file_name}] ===\n{content}\n"
            except: pass
        elif file_name.lower().endswith('.txt') and file_name != "requirements.txt":
            try:
                with open(file_name, 'r', encoding='utf-8') as f: content = f.read()
            except:
                with open(file_name, 'r', encoding='cp949') as f: content = f.read()
            general_rules += f"\n\n=== [참고 자료: {file_name}] ===\n{content}\n"
    return org_text, general_rules, intranet_guide

ORG_CHART_DATA, COMPANY_RULES, INTRANET_GUIDE = load_data()

# 업무 분장 데이터 (2026-01-02 기반)
WORK_DISTRIBUTION = """
[경영관리본부 업무 분장표]
- 이경한 매니저: 사옥/법인차량 관리, 현장 숙소 관리, 근태 관리, 행사 기획/실행, 제증명 발급, 지출결의(출장/숙소), 간식구매
- 김병찬 매니저: 제도 공지, 위임전결, 취업규칙, 평가보상
- 백다영 매니저: 교육(리더/법정), 채용, 입퇴사 안내
- 김승민 책임: 품의서 관리, 세금계산서, 법인카드 비용처리, 숙소 비용 집행
- 안하련 매니저: 급여 서류(원천징수), 품의 금액 송금
- 손경숙 매니저: 비품 구매
- 최관식 매니저: 내부 직원 정보 관리 (어울지기, 플로우)
"""

# --------------------------------------------------------------------------
# [2] 외부 서비스 설정
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
    _, center_col, _ = st.columns([1, 4, 1])
    with center_col:
        st.header("🔒 임직원 접속 (신원확인)")
        with st.form("login_form"):
            input_name = st.text_input("성명")
            input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
            st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")

            if st.form_submit_button("접속하기", use_container_width=True):
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
    
    # --- 좌측 패널(사이드바) 최적화 ---
    with st.sidebar:
        # 로고 영역 (이미지 파일 준비 시 경로를 수정하세요)
        # st.image("logo.png", use_column_width=True) 
        st.markdown("<h2 style='text-align: center; color: #E74C3C;'>🏢 KCIM</h2>", unsafe_allow_html=True)
        st.markdown("---")
        
        st.subheader("👤 접속 정보")
        st.success(f"**{user['name']} {user['rank']}**")
        st.markdown(f"<p class='sidebar-dept'>🏢 {user['dept']}</p>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # [수정 사항] 이미지 카테고리 기반 주요 서비스 안내
        st.subheader("🚀 주요 서비스 안내")
        st.markdown("""
        <div class='service-item'>🛠️ <b>시설/수리</b>: 사옥·차량 유지보수, 장비 교체</div>
        <div class='service-item'>👤 <b>입퇴사/이동</b>: 제증명, 인사발령, 채용 문의</div>
        <div class='service-item'>📋 <b>프로세스/규정</b>: 사내규정, 시스템 사용 이슈</div>
        <div class='service-item'>🎁 <b>복지/휴가</b>: 복리후생, 경조사, 교육 지원</div>
        <div class='service-item'>📢 <b>불편사항</b>: 근무 환경 컴플레인 및 개선</div>
        <div class='service-item'>💬 <b>일반/기타</b>: 단순 질의 및 업무 협조 요청</div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # --- 메인 채팅 화면 ---
    if "messages" not in st.session_state:
        greeting_html = f"""
        <div style="margin-top: 20px;">
            <p class="greeting-title">{user['name']} {user['rank']}님, 반갑습니다! 👋</p>
            <p class="greeting-subtitle">오늘은 <b>복지, 규정, 시설 문의</b> 등 무엇을 도와드릴까요?</p>
        </div>
        """
        st.session_state["messages"] = [{"role": "assistant", "content": greeting_html, "is_html": True}]
    
    if "awaiting_confirmation" not in st.session_state: st.session_state["awaiting_confirmation"] = False

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg.get("is_html"):
                st.markdown(msg["content"], unsafe_allow_html=True)
            else:
                st.write(msg["content"])

    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        if st.session_state["awaiting_confirmation"]:
            if check_finish_intent(prompt) == "FINISH":
                st.chat_message("assistant").write(f"도움이 되어 기쁩니다. {user['name']} {user['rank']}님, 즐거운 하루 보내세요! 😊")
                st.session_state["awaiting_confirmation"] = False
                st.stop()
            else:
                st.session_state["awaiting_confirmation"] = False

        if not st.session_state["awaiting_confirmation"]:
            system_instruction = f"""
            너는 1990년 창립된 건설 IT 선도 기업 KCIM의 HR/총무 AI 매니저야.
            임직원 {user['name']} {user['rank']}님에게 친절하고 정중하게 답변해줘.

            [사내 데이터]
            {ORG_CHART_DATA}
            {COMPANY_RULES}
            {INTRANET_GUIDE}
            {WORK_DISTRIBUTION}

            [원칙]
            1. 안내 번호: 02-772-5806.
            2. 담당자 언급: 성함 뒤에 반드시 '매니저' 또는 '책임' 직급을 붙여 호칭해.
            3. 시설/차량/숙소: "HR팀 이경한 매니저에게 문의바랍니다." 안내 및 [ACTION] 태그 포함.
            4. 답변 끝에 반드시 [CATEGORY:분류명] 태그 포함. (이미지의 카테고리명 활용: 시설/수리, 입퇴사/이동, 프로세스/규정, 복지/휴가, 불편사항, 일반/기타)
            """
            
            try:
                completion = client.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                )
                raw_response = completion.choices[0].message.content
            except:
                raw_response = "시스템 오류가 발생했습니다. 잠시 후 시도해주세요."

            category = re.search(r'\[CATEGORY:(.*?)\]', raw_response).group(1) if "[CATEGORY:" in raw_response else "기타"
            final_status = "담당자확인필요" if "[ACTION]" in raw_response else "처리완료"
            clean_ans = raw_response.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
            
            save_to_sheet(user['dept'], user['name'], user['rank'], category, summarize_text(prompt), summarize_text(clean_ans), final_status)

            full_response = clean_ans + f"\n\n**{user['name']} {user['rank']}님, 더 궁금하신 점이 있으실까요?**"
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            with st.chat_message("assistant"):
                st.write(full_response)
            st.session_state["awaiting_confirmation"] = True
