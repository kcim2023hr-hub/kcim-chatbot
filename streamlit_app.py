import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
import re

# 1. 페이지 설정: 중앙 정렬 레이아웃 및 타이틀 고정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 및 여백 최적화 커스텀 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }
    
    /* 로그인 폼 카드 스타일 */
    div[data-testid="stForm"] { background-color: #ffffff; padding: 50px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; text-align: center; }
    
    /* 사이드바 디자인 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    .sidebar-user-box { background-color: #f8f9fa; padding: 20px; border-radius: 15px; border: 1px solid #edf0f2; margin-bottom: 20px; text-align: center; }
    
    /* 카테고리 버튼 가독성 */
    div[data-testid="stSidebar"] .stButton > button { background-color: #ffffff !important; border: 1px solid #e9ecef !important; padding: 18px 15px !important; border-radius: 15px !important; width: 100% !important; margin-bottom: -5px !important; }
    
    /* 중앙 플랫 인사말 디자인 */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 21px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 규정 파일 지식 베이스 및 다운로드 매핑 (docs & doa 폴더 트리 반영)
# --------------------------------------------------------------------------
COMPANY_DOCUMENTS_INFO = """
[KCIM 사내 규정 검색 가이드라인]
1. 일반 규정 (docs/): 2026년_복지제도.pdf, 2025년 달라지는 육아지원제도(고용노동부).pdf, 취업규칙(2025년)_케이씨아이엠.pdf, 2024_재택근무_운영규정(최종본).pdf, 사고발생처리 매뉴얼(2023년).pdf
2. 위임전결규정 (docs/doa/): doa_0_overview.pdf 부터 doa_12_consulting.pdf 까지 총 13종 (전사 공통 및 부서별 권한)
3. 기타 자료 (docs/): [KCIM] 계약서 검토 프로세스 안내.pdf, 사업자등록증(KCIM).pdf, [사내 와이파이(Wifi) 정보 및 비밀번호].txt, [경영관리본부 업무 분장표].txt
"""

RULES_LIST = [
    "2026년_복지제도.pdf", "2025년 달라지는 육아지원제도(고용노동부).pdf", "취업규칙(2025년)_케이씨아이엠.pdf",
    "doa_0_overview.pdf", "doa_1_common.pdf", "doa_2_management.pdf", "doa_3_system.pdf",
    "doa_4_hr.pdf", "doa_5_tech.pdf", "doa_6_strategy.pdf", "doa_7_cx.pdf", "doa_8_solution.pdf",
    "doa_9_hitech.pdf", "doa_10_bim.pdf", "doa_11_ts.pdf", "doa_12_consulting.pdf",
    "2024_재택근무_운영규정(최종본).pdf", "[KCIM] 계약서 검토 프로세스 안내.pdf", "사업자등록증(KCIM).pdf",
    "사고발생처리 매뉴얼(2023년).pdf", "[사내 와이파이(Wifi) 정보 및 비밀번호].txt", "[경영관리본부 업무 분장표].txt"
]

# --------------------------------------------------------------------------
# [2] 유틸리티 기능 (KST 보정, 요약, 시트 저장)
# --------------------------------------------------------------------------
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def get_dynamic_greeting():
    now_hour = get_kst_now().hour
    if 5 <= now_hour < 11: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 11 <= now_hour < 14: return "즐거운 점심시간입니다. 맛있는 식사 하셨나요? 🍱"
    elif 14 <= now_hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    elif 18 <= now_hour < 22: return "오늘 하루도 고생 많으셨습니다! ✨"
    else: return "늦은 시간까지 수고가 많으시네요. 🌙"

def summarize_text(text):
    if not text or len(text.strip()) == 0: return "-"
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "핵심 한 줄 요약가."}, {"role": "user", "content": text}],
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
# [3] UI 실행 및 대화 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []

# [로그인 화면]
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
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
    with st.sidebar:
        st.markdown("<div style='text-align: center; width: 100%;'><h2>🏢 KCIM</h2></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='sidebar-user-box'><b>{user['name']} {user['rank']}</b><br>{user['dept']}</div>", unsafe_allow_html=True)
        if st.button("✅ 새 상담 시작", use_container_width=True):
            st.session_state["messages"] = []
            st.rerun()
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    if not st.session_state.messages:
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{get_dynamic_greeting()}</p></div>", unsafe_allow_html=True)

    # 대화 렌더링 (지능형 경로 반영)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                for f_name in RULES_LIST:
                    if f_name in msg["content"]:
                        # [핵심] 폴더 경로 자동 분기 로직
                        f_path = f"docs/doa/{f_name}" if f_name.startswith("doa_") else f"docs/{f_name}"
                        if os.path.exists(f_path):
                            with open(f_path, "rb") as f:
                                st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"dl_{f_name}_{msg['content'][:5]}")

    # 채팅 입력 및 답변 생성
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        with st.spinner("HR 담당자가 규정을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                sys_msg = f"너는 1990년 창립된 KCIM의 HR팀장이야. {user['name']}님께 정중히 답변해.\n{COMPANY_DOCUMENTS_INFO}\n마지막에 [CATEGORY:분류] 필수."
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                answer = res.choices[0].message.content
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "기타"
                clean_ans = answer.replace(f"[CATEGORY:{category}]", "").strip()
                
                with st.chat_message("assistant"):
                    st.write(clean_ans)
                    for f_name in RULES_LIST:
                        if f_name in clean_ans:
                            # [핵심] 위임전결규정은 doa 폴더에서 탐색
                            f_path = f"docs/doa/{f_name}" if f_name.startswith("doa_") else f"docs/{f_name}"
                            if os.path.exists(f_path):
                                with open(f_path, "rb") as f:
                                    st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"new_dl_{f_name}")

                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                save_to_sheet(user['dept'], user['name'], user['rank'], category, summarize_text(prompt), summarize_text(clean_ans), "처리완료")
            except Exception as e:
                st.error(f"오류: {e}")
