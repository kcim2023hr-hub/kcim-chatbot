import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
import re

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 커스텀 CSS (기존 유지 및 보정) ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 2rem !important; }
    div[data-testid="stForm"] { background-color: #ffffff; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; }
    .sidebar-user-box { background-color: #f8f9fa; padding: 15px; border-radius: 12px; border: 1px solid #edf0f2; margin-bottom: 20px; text-align: center; }
    .greeting-container { text-align: center; margin-bottom: 30px; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 지식 베이스 및 데이터 로드 (기존 유지)
# --------------------------------------------------------------------------
COMPANY_DOCUMENTS_INFO = """
[KCIM 최신 사내 규정]
1. 2025년_복지제도.pdf, 2. 육아지원제도.pdf, 3. 현장근무지원금.pdf 등 (생략)
"""

@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {"관리자": {"pw": "1323", "dept": "HR팀", "rank": "매니저"}}
    if os.path.exists(file_name):
        try:
            df = pd.read_excel(file_name, engine='openpyxl')
            for _, row in df.iterrows():
                name = str(row['이름']).strip()
                phone = str(row['휴대폰 번호']).strip()
                db[name] = {"pw": phone[-4:] if len(phone) >=4 else "0000", 
                            "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [2] 유틸리티 기능 (KST 보정, 요약, 시트 저장)
# --------------------------------------------------------------------------
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def summarize_text(text):
    if not text or len(text.strip()) == 0: return "-"
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "핵심 요약문으로 변환해줘."}, {"role": "user", "content": text}],
            temperature=0
        )
        return res.choices[0].message.content.strip()
    except: return text[:30]
    
def save_to_sheet(dept, name, rank, category, question, answer, status):
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("응답시트")
        sheet.append_row([get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status])
    except: pass

# --------------------------------------------------------------------------
# [3] 메인 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []

# [로그인 화면]
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM 임직원 챗봇</h2>", unsafe_allow_html=True)
        input_name = st.text_input("성명")
        input_pw = st.text_input("비밀번호 (뒷 4자리)", type="password")
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {**EMPLOYEE_DB[input_name], "name": input_name}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")

# [챗봇 화면]
else:
    user = st.session_state["user_info"]
    
    # 사이드바 설정
    with st.sidebar:
        st.markdown(f"<div class='sidebar-user-box'><b>{user['name']} {user['rank']}</b><br>{user['dept']}</div>", unsafe_allow_html=True)
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 채팅 헤더
    st.markdown(f"### 🤖 KCIM HR AI 매니저")
    st.caption("1990년 창립 이래 건설 IT를 선도해온 KCIM의 지식 베이스로 답변합니다.")

    # 1. 기존 대화 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 2. 사용자 입력 처리
    if prompt := st.chat_input("궁금한 점을 입력하세요 (예: 올해 복지 제도가 뭐야?)"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # 3. 답변 생성
        with st.spinner("규정을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                sys_msg = f"너는 KCIM의 HR 매니저야. 아래 규정을 참고해 답변해.\n{COMPANY_DOCUMENTS_INFO}\n답변 끝에 [CATEGORY:분류]를 달아줘."
                
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages
                )
                answer = res.choices[0].message.content
                
                # 태그 추출 로직
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "일반"
                status = "담당자 확인 필요" if "[ACTION]" in answer else "처리완료"
                clean_ans = answer.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()

                with st.chat_message("assistant"):
                    st.write(clean_ans)

                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                
                # 시트 저장 (백그라운드)
                q_sum = summarize_text(prompt)
                a_sum = summarize_text(clean_ans)
                save_to_sheet(user['dept'], user['name'], user['rank'], category, q_sum, a_sum, status)
                
            except Exception as e:
                st.error(f"오류: {e}")
