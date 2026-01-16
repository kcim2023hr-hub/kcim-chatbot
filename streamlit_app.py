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

# --- UI 커스텀 CSS (디자인 절대 유지) ---
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
# [1] 규정 및 양식 파일 지식 베이스
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# [1] 규정 및 양식 파일 지식 베이스 (상세 규정 내용 보강)
# --------------------------------------------------------------------------
COMPANY_DOCUMENTS_INFO = """
[KCIM HR 규정 및 양식 핵심 가이드]

1. [휴가 및 복지]
   - **배우자 출산 휴가**: 법적 기준에 따라 '유급 20일' 부여 (최우선 답변). 필요시 'KCIM_가족돌봄 휴가신청서.xlsx' 사용.
   - **가족돌봄휴가**: 가족(부모,자녀,배우자 등)의 질병/사고/노령으로 돌봄 필요 시 사용. 연간 최장 90일(무급). 양식: 'KCIM_가족돌봄 휴가신청서.xlsx'
   - **난임치료휴가**: 연간 3일(최초 1일 유급). 양식: 'KCIM_난임치료휴가 신청서.xlsx'
   - **성장포인트**: 자기개발/도서구입 등에 사용 가능. 양식: 'KCIM_성장포인트 적립 및 사용 신청서.xlsx'
   - **자녀 학자금**: 고등학교/대학교 자녀 학비 지원 (상세 기준은 2026년_복지제도.pdf 참조).

2. [근무 및 행정]
   - **재택근무**: 부서장 승인 필요, 주 1~2회 가능. 규정: '2024_재택근무_운영규정(최종본).pdf'
   - **법인차량**: 차량 반납/인계 시 'KCIM_법인차량_인수인계서.xlsx' 작성 필수. 파손 시 'KCIM_사고경위서.xlsx' 작성.
   - **명함 신청**: 신규/재발급 필요 시 'KCIM_명함신청양식.xlsx' 작성 후 경영지원팀 제출.
   - **기안서**: 비용 발생이나 대외 공문 발송 전 내부 승인용. 양식: 'KCIM_기안서.xlsx'

3. [프로젝트 및 계약]
   - **BIM 프로젝트 종료**: 프로젝트 완료 시 산출물 및 이슈 정리하여 보고. 양식: 'KCIM_BIM 프로젝트 종료 프로세스 & 결과 보고서.xlsx'
   - **업무 인수인계**: 부서 이동이나 퇴사 시 필수 작성. 양식: 'KCIM_BIM 프로젝트 업무 인수인계서.xlsx'

4. [인사 명령/이동]
   - **부서 이동**: 본인 희망 혹은 조직 개편 시 작성. 양식: 'KCIM_부서이동요청서.xlsx'
   - **겸직 허가**: 회사 업무 외 영리 활동 시 사전 승인 필수. 양식: 'KCIM_겸직허가신청서.xlsx'
   - **사직/복직**: 퇴사 30일 전 제출(KCIM_사직서.xlsx), 휴직 후 복귀 시(KCIM_복직원.xlsx)

[답변 지침]
- 위 내용을 바탕으로 질문자에게 구체적인 일수, 조건, 절차를 문장으로 설명하세요.
- 설명 후 관련된 '파일명'을 정확히 언급하여 다운로드 버튼을 유도하세요.
"""

RULES_LIST = [
    "2026년_복지제도.pdf", "2025년 달라지는 육아지원제도(고용노동부).pdf", "취업규칙(2025년)_케이씨아이엠.pdf",
    "doa_0_overview.pdf", "doa_1_common.pdf", "doa_2_management.pdf", "doa_3_system.pdf",
    "doa_4_hr.pdf", "doa_5_tech.pdf", "doa_6_strategy.pdf", "doa_7_cx.pdf", "doa_8_solution.pdf",
    "doa_9_hitech.pdf", "doa_10_bim.pdf", "doa_11_ts.pdf", "doa_12_consulting.pdf",
    "2024_재택근무_운영규정(최종본).pdf", "[KCIM] 계약서 검토 프로세스 안내.pdf", "사업자등록증(KCIM).pdf",
    "사고발생처리 매뉴얼(2023년).pdf", "[사내 와이파이(Wifi) 정보 및 비밀번호].txt", "[경영관리본부 업무 분장표].txt",
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
    elif 14 <= hr < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    else: return "오늘 하루도 고생 많으셨습니다! ✨"

def summarize_text(text):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "핵심 요약 전문가."}, {"role": "user", "content": text}], temperature=0)
        return res.choices[0].message.content.strip()
    except: return "-"

def save_to_sheet(dept, name, rank, category, question, answer, status):
    url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(url).worksheet("응답시트")
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
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

# [로그인 화면] - 안내 문구 복구
if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        u_name = st.text_input("성명", placeholder="이름 입력")
        u_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
        if st.form_submit_button("접속하기", use_container_width=True):
            if u_name in EMPLOYEE_DB and EMPLOYEE_DB[u_name]["pw"] == u_pw:
                st.session_state["logged_in"], st.session_state["user_info"] = True, {**EMPLOYEE_DB[u_name], "name": u_name}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>{user['dept']}</span></div>", unsafe_allow_html=True)
        
        # 관리자 전용 메뉴
        if user['name'] == "관리자":
            st.markdown("---")
            st.subheader("⚙️ 관리자 전용")
            with st.expander("📊 실시간 민원 현황 보기"):
                try:
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
                    url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
                    sheet = gspread.authorize(creds).open_by_url(url).worksheet("응답시트")
                    st.dataframe(pd.DataFrame(sheet.get_all_records()).tail(10))
                except: st.warning("데이터 로드 실패")
            if os.path.exists('members.xlsx'):
                with open('members.xlsx', "rb") as f:
                    st.download_button("📥 인사 DB 다운로드", f, file_name="members_backup.xlsx")

        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "사옥·차량 유지보수, 수리 요청"), ("👤 입퇴사/이동", "제증명, 인사 발령, 채용 문의"), ("📋 프로세스/규정", "사내 규정, 시스템 및 보안"), ("🎁 복지/휴가", "경조사, 지원금, 휴가 및 동호회"), ("📢 불편사항", "근무 환경 내 불편 사항"), ("💬 일반/기타", "단순 질의 및 협조")]
        
        for title, desc in cats:
            if st.button(f"{title}\n{desc}", key=title, disabled=st.session_state["inquiry_active"]):
                st.session_state["inquiry_active"] = True
                st.session_state.messages.append({"role": "assistant", "content": f"[{title}] 주제 상담을 시작합니다."})
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.session_state["inquiry_active"]:
            if st.button("✅ 상담 종료", use_container_width=True):
                st.session_state["inquiry_active"], st.session_state["messages"] = False, []
                st.rerun()
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.clear(); st.rerun()
        st.markdown("<p class='beta-notice'>※베타 테스트중입니다.:)</p>", unsafe_allow_html=True)

    if not st.session_state.messages:
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{get_dynamic_greeting()}</p></div>", unsafe_allow_html=True)

    # 대화 렌더링 및 3단 분기 경로 로직
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                for f_name in RULES_LIST:
                    if f_name in msg["content"]:
                        if f_name.startswith("doa_"): path = f"docs/doa/{f_name}"
                        elif f_name.startswith("KCIM"): path = f"docs/forms/{f_name}"
                        else: path = f"docs/{f_name}"
                        if os.path.exists(path):
                            with open(path, "rb") as f:
                                st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"dl_{f_name}_{msg['content'][:5]}")

    # 채팅 입력 및 직접 답변 로직 강화
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        sys_msg = f"""너는 1990년 창립된 KCIM의 HR팀 팀장이야. {user['name']}님께 답변해줘.
        [핵심 원칙]
        1. 배우자 출산 휴가는 반드시 **'총 20일(유급)'**로 안내해.
        2. "파일을 보라"는 말 금지. 규정 내용을 네가 직접 요약해서 문장으로 해답을 말해줘.
        3. 외부 정보는 최신 근로기준법을 참고하고 출처를 밝혀줘.
        4. 관련 양식(KCIM_...) 파일명을 답변에 포함해.
        5. 마지막에 [CATEGORY:분류명] 필수.
        
        {COMPANY_DOCUMENTS_INFO}
        """
        
        with st.spinner("HR 담당자가 규정을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                answer = res.choices[0].message.content
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "기타"
                clean_ans = answer.replace(f"[CATEGORY:{category}]", "").strip()
                
                with st.chat_message("assistant"):
                    st.write(clean_ans)
                    for f_name in RULES_LIST:
                        if f_name in clean_ans:
                            if f_name.startswith("doa_"): path = f"docs/doa/{f_name}"
                            elif f_name.startswith("KCIM"): path = f"docs/forms/{f_name}"
                            else: path = f"docs/{f_name}"
                            if os.path.exists(path):
                                with open(path, "rb") as f:
                                    st.download_button(label=f"📂 {f_name} 다운로드", data=f, file_name=f_name, key=f"new_{f_name}")

                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                save_to_sheet(user['dept'], user['name'], user['rank'], category, summarize_text(prompt), summarize_text(clean_ans), "처리완료")
                st.rerun() 
            except Exception as e: st.error(f"오류: {e}")
