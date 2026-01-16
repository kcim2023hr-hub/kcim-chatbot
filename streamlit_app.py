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

# --- UI 커스텀 CSS (디자인 유지) ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }
    div[data-testid="stForm"] { background-color: #ffffff; padding: 50px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; text-align: center; }
    div[data-testid="stNotification"] { font-size: 16px; background-color: #f0f7ff; border-radius: 12px; color: #0056b3; padding: 20px; }
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    .sidebar-user-box { background-color: #f8f9fa; padding: 20px; border-radius: 15px; border: 1px solid #edf0f2; margin-bottom: 20px; text-align: center; }
    div[data-testid="stSidebar"] .stButton > button { background-color: #ffffff !important; border: 1px solid #e9ecef !important; padding: 18px 15px !important; border-radius: 15px !important; width: 100% !important; margin-bottom: -5px !important; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p { font-size: 13px; color: #666; line-height: 1.5; white-space: pre-line; text-align: left; margin: 0; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p::first-line { font-size: 16px; font-weight: 700; color: #1a1c1e; }
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 60px !important; line-height: 1.6; }
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 21px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 규정 및 양식 파일 지식 베이스 (27종 양식 추가)
# --------------------------------------------------------------------------
COMPANY_DOCUMENTS_INFO = """
[KCIM 최신 사내 규정 및 양식 지식]
1. 일반 규정 (docs/): 2026년_복지제도.pdf, 취업규칙(2025년)_케이씨아이엠.pdf, 2024_재택근무_운영규정.pdf 등
2. 위임전결규정 (docs/doa/): doa_0_overview.pdf ~ doa_12_consulting.pdf (총 13종)
3. 각종 양식 및 서식 (docs/forms/):
   - HR 관련: 가족돌봄/난임치료 휴가신청서, 사직서, 복직원, 부서이동요청서, 채용계획서, 신입사원 평가표 등
   - 프로젝트/계약: BIM용역 계약서(도급/수급), 프로젝트 인수인계서 및 종료 보고서 등
   - 일반 행정: 기안서, 공문(국/영문), 위임장, 사고경위서, 명함신청양식, 법인차량 인수인계서 등
"""

# 전체 파일 리스트 (경로 추적용)
RULES_LIST = [
    # 일반 및 DOA
    "2026년_복지제도.pdf", "2025년 달라지는 육아지원제도(고용노동부).pdf", "취업규칙(2025년)_케이씨아이엠.pdf",
    "doa_0_overview.pdf", "doa_1_common.pdf", "doa_2_management.pdf", "doa_3_system.pdf",
    "doa_4_hr.pdf", "doa_5_tech.pdf", "doa_6_strategy.pdf", "doa_7_cx.pdf", "doa_8_solution.pdf",
    "doa_9_hitech.pdf", "doa_10_bim.pdf", "doa_11_ts.pdf", "doa_12_consulting.pdf",
    "2024_재택근무_운영규정(최종본).pdf", "[KCIM] 계약서 검토 프로세스 안내.pdf", "사업자등록증(KCIM).pdf",
    "사고발생처리 매뉴얼(2023년).pdf", "[사내 와이파이(Wifi) 정보 및 비밀번호].txt", "[경영관리본부 업무 분장표].txt",
    # docs/forms 폴더 내 신규 양식 27종
    "KCIM BIM용역 계약서_도급인기준.docx", "KCIM BIM용역 계약서_수급인기준.docx", "KCIM_BIM 프로젝트 업무 인수인계서.xlsx",
    "KCIM_BIM 프로젝트 종료 프로세스 & 결과 보고서.xlsx", "KCIM_가족돌봄 휴가신청서.xlsx", "KCIM_겸직허가신청서.xlsx",
    "KCIM_공문(국문).docx", "KCIM_공문(영문).docx", "KCIM_기안서.xlsx", "KCIM_난임치료휴가 신청서.xlsx",
    "KCIM_명함신청양식.xlsx", "KCIM_법인차량_인수인계서.xlsx", "KCIM_복직원.xlsx", "KCIM_부서이동요청서.xlsx",
    "KCIM_사고경위서.xlsx", "KCIM_사전휴가계 사용 및 상계합의서.xlsx", "KCIM_사직서.xlsx",
    "KCIM_성장포인트 적립 및 사용 신청서.xlsx", "KCIM_숙소지원금 변경신청서.xlsx", "KCIM_신입사원 3Month 계획 및 평가.xlsx",
    "KCIM_워크샵 계획서,결과보고서.xlsx", "KCIM_위임장.docx", "KCIM_이의신청서.xlsx",
    "KCIM_임신▪육아기 관련 지원 신청서.xlsx", "KCIM_채용계획서_채용요청서.xlsx", "KCIM_해외 인사발령 예정통지서.xlsx",
    "KCIM_행사 불참사유서.xlsx"
]

# --------------------------------------------------------------------------
# [2] 유틸리티 기능
# --------------------------------------------------------------------------
def get_kst_now(): return datetime.now(timezone(timedelta(hours=9)))

def get_dynamic_greeting():
    hr = get_kst_now().hour
    if 5 <= hr < 11: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 11 <= hr < 14: return "즐거운 점심시간입니다. 맛있는 식사 하셨나요? 🍱"
    elif 14 <= hr < 18: return "즐거운 오후입니다. 무엇을 도와드릴까요? ☕"
    else: return "오늘 하루도 고생 많으셨습니다! ✨"

def summarize_text(text):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "핵심 한 줄 요약 전문가."}, {"role": "user", "content": text}], temperature=0)
        return res.choices[0].message.content.strip()
    except: return "-"

def save_to_sheet(dept, name, rank, category, question, answer, status):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url("https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit").worksheet("응답시트")
        sheet.append_row([get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status])
    except: pass

@st.cache_data
def load_employee_db():
    db = {"관리자": {"pw": "1323", "dept": "HR팀", "rank": "매니저"}}
    if os.path.exists('members.xlsx'):
        try:
            df = pd.read_excel('members.xlsx', engine='openpyxl')
            for _, row in df.iterrows():
                n = str(row['이름']).strip()
                db[n] = {"pw": str(row['휴대폰 번호'])[-4:] if len(str(row['휴대폰 번호'])) >=4 else "0000", "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [3] UI 및 대화 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []

if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        u_name, u_pw = st.text_input("성명"), st.text_input("비밀번호 (뒷 4자리)", type="password")
        if st.form_submit_button("접속하기", use_container_width=True):
            if u_name in EMPLOYEE_DB and EMPLOYEE_DB[u_name]["pw"] == u_pw:
                st.session_state["logged_in"], st.session_state["user_info"] = True, {**EMPLOYEE_DB[u_name], "name": u_name}
                st.rerun()
            else: st.error("정보 불일치")
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b>{user['name']} {user['rank']}</b><br><span>{user['dept']}</span></div>", unsafe_allow_html=True)
        if st.button("✅ 새 상담 시작", use_container_width=True): st.session_state["messages"] = []; st.rerun()
        if st.button("🚪 로그아웃", use_container_width=True): st.session_state.clear(); st.rerun()
        st.markdown("<p class='beta-notice'>※베타 테스트중입니다.</p>", unsafe_allow_html=True)

    if not st.session_state.messages:
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{get_dynamic_greeting()}</p></div>", unsafe_allow_html=True)

    # 대화 렌더링 (지능형 경로 분기: docs, doa, forms)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                for f_name in RULES_LIST:
                    if f_name in msg["content"]:
                        # 경로 결정 로직
                        if f_name.startswith("doa_"): p = f"docs/doa/{f_name}"
                        elif f_name.startswith("KCIM"): p = f"docs/forms/{f_name}"
                        else: p = f"docs/{f_name}"
                        
                        if os.path.exists(p):
                            with open(p, "rb") as f: st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"dl_{f_name}_{msg['content'][:5]}")

    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        sys_msg = f"""너는 1990년 창립된 KCIM의 HR팀 팀장이야. {user['name']}님께 정중히 답변해줘.
        [핵심 지침]
        1. 아래 규정 및 양식 목록을 바탕으로 '직접 답변'을 제공해. "파일을 보라"는 말보다 내용을 요약 설명하는 것이 우선이야.
        2. 사용자가 특정 신청이나 보고를 원하면, 해당 양식 파일명을 정확히 언급하여 다운로드 버튼이 생기게 해.
        3. 답변 마지막에 [CATEGORY:분류] 필수.
        
        {COMPANY_DOCUMENTS_INFO}
        """
        
        with st.spinner("HR 담당자가 내용을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                ans = res.choices[0].message.content
                cat = re.search(r'\[CATEGORY:(.*?)\]', ans).group(1) if "[CATEGORY:" in ans else "기타"
                clean_ans = ans.replace(f"[CATEGORY:{cat}]", "").strip()
                
                with st.chat_message("assistant"):
                    st.write(clean_ans)
                    for f_name in RULES_LIST:
                        if f_name in clean_ans:
                            if f_name.startswith("doa_"): p = f"docs/doa/{f_name}"
                            elif f_name.startswith("KCIM"): p = f"docs/forms/{f_name}"
                            else: p = f"docs/{f_name}"
                            
                            if os.path.exists(p):
                                with open(p, "rb") as f: st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"new_{f_name}")

                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                save_to_sheet(user['dept'], user['name'], user['rank'], cat, summarize_text(prompt), summarize_text(clean_ans), "처리완료")
                st.rerun() 
            except Exception as e: st.error(f"오류: {e}")
