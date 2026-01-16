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
    div[data-testid="stNotification"] { font-size: 16px; background-color: #f0f7ff; border-radius: 12px; color: #0056b3; padding: 20px; }
    
    /* 사이드바 디자인 및 로고 중앙 정렬 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    .sidebar-user-box { background-color: #f8f9fa; padding: 20px; border-radius: 15px; border: 1px solid #edf0f2; margin-bottom: 20px; text-align: center; }
    
    /* 카테고리 버튼 가독성 고정 */
    div[data-testid="stSidebar"] .stButton > button { background-color: #ffffff !important; border: 1px solid #e9ecef !important; padding: 18px 15px !important; border-radius: 15px !important; width: 100% !important; margin-bottom: -5px !important; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p { font-size: 13px; color: #666; line-height: 1.5; white-space: pre-line; text-align: left; margin: 0; }
    div[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p::first-line { font-size: 16px; font-weight: 700; color: #1a1c1e; }
    
    /* 베타 테스트 안내 문구 상단 여백 확대 */
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 60px !important; line-height: 1.6; }

    /* 중앙 플랫 인사말 디자인 */
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
※ 중요 업데이트: 배우자 출산 휴가는 총 20일(유급)입니다. 파일 내용보다 이 지침을 우선하세요.

1. 일반 규정 (경로: docs/)
   - 2026년_복지제도.pdf, 취업규칙(2025년)_케이씨아이엠.pdf, 2024_재택근무_운영규정(최종본).pdf
2. 위임전결규정 (경로: docs/doa/)
   - doa_0_overview.pdf ~ doa_12_consulting.pdf (총 13종)
3. 각종 양식 (경로: docs/forms/)
   - [HR/휴가]: KCIM_가족돌봄 휴가신청서(간병,자녀돌봄), KCIM_난임치료휴가 신청서(시술), KCIM_사직서, KCIM_복직원, KCIM_임신▪육아기 관련 지원 신청서, KCIM_부서이동요청서, KCIM_겸직허가신청서, KCIM_행사 불참사유서, KCIM_이의신청서
   - [업무/공통]: KCIM_기안서(결재), KCIM_공문(국문/영문), KCIM_위임장, KCIM_명함신청양식, KCIM_사고경위서, KCIM_법인차량_인수인계서, KCIM_워크샵 계획서,결과보고서
   - [프로젝트]: KCIM BIM용역 계약서(도급/수급), KCIM_BIM 프로젝트 업무 인수인계서, KCIM_BIM 프로젝트 종료 프로세스 & 결과 보고서
   - [보상/채용]: KCIM_성장포인트 적립 및 사용 신청서, KCIM_숙소지원금 변경신청서, KCIM_채용계획서_채용요청서, KCIM_신입사원 3Month 계획 및 평가
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
# [2] 유틸리티 기능 (KST 보정, 요약, 시트 저장)
# --------------------------------------------------------------------------
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def get_dynamic_greeting():
    now_hour = get_kst_now().hour
    if 5 <= now_hour < 11: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 11 <= now_hour < 14: return "즐거운 점심시간입니다. 맛있는 식사 하셨나요? 🍱"
    elif 14 <= now_hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    elif 18 <= now_hour < 22: return "오늘 하루도 고생 많으셨습니다! 마무리하며 도와드릴 일이 있을까요? ✨"
    else: return "늦은 시간까지 수고가 많으시네요. 무엇을 도와드릴까요? 🌙"

def summarize_text(text):
    if not text or len(text.strip()) == 0: return "-"
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 전문 요약가야. 입력받은 문장을 한 줄의 핵심 요약문으로 변환해줘."},
                {"role": "user", "content": f"다음 문장을 요약해줘: {text}"}
            ],
            temperature=0
        )
        return res.choices[0].message.content.strip()
    except: return text[:30] + "..."

def save_to_sheet(dept, name, rank, category, question, answer, status):
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("응답시트")
        sheet.append_row([get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), dept, name, rank, category, question, answer, status])
    except: pass

# --------------------------------------------------------------------------
# [3] 데이터 로드 (KCIM 1990년 창립 및 인사 데이터 반영)
# --------------------------------------------------------------------------
@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {"관리자": {"pw": "1323", "dept": "HR팀", "rank": "매니저"}}
    if os.path.exists(file_name):
        try:
            df = pd.read_excel(file_name, engine='openpyxl')
            for _, row in df.iterrows():
                name = str(row['이름']).strip()
                db[name] = {"pw": str(row['휴대폰 번호'])[-4:] if len(str(row['휴대폰 번호'])) >=4 else "0000", 
                            "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [4] UI 실행 및 대화 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

if not st.session_state["logged_in"]:
    with st.form("login_form"):
        st.markdown("<h2 style='text-align: center; color: #1a1c1e;'>🏢 KCIM 임직원 민원 챗봇</h2>", unsafe_allow_html=True)
        input_name = st.text_input("성명", placeholder="이름 입력")
        input_pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password", placeholder="****")
        st.info("💡 민원 데이터 관리를 위해 해당 임직원 신원 확인을 요청드립니다.")
        if st.form_submit_button("접속하기", use_container_width=True):
            if input_name in EMPLOYEE_DB and EMPLOYEE_DB[input_name]["pw"] == input_pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {**EMPLOYEE_DB[input_name], "name": input_name}
                st.rerun()
            else: st.error("정보가 일치하지 않습니다.")
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown("<div style='text-align: center; width: 100%;'><h2 style='color: #1a1c1e; margin-bottom: 20px;'>🏢 KCIM</h2></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>HR팀</span></div>", unsafe_allow_html=True)
            
            # --- 관리자 전용 메뉴 (이름이 '관리자'일 때만 노출) ---
        if user['name'] == "관리자":
            st.markdown("---")
            st.subheader("⚙️ 관리자 전용")
            
            # 1. 실시간 시트 확인 (익스팬더로 깔끔하게 처리)
            with st.expander("📊 실시간 민원 현황 보기"):
                try:
                    # 구글 시트 데이터를 가져와서 표로 보여줌
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
                    sheet = gspread.authorize(creds).open_by_url("매니저님의시트URL").worksheet("응답시트")
                    df = pd.DataFrame(sheet.get_all_records())
                    st.dataframe(df.tail(10)) # 최근 10건만 표시
                except:
                    st.warning("시트 데이터를 불러올 수 없습니다.")
            
            # 2. 인사 DB 다운로드
            if os.path.exists('members.xlsx'):
                with open('members.xlsx', "rb") as f:
                    st.download_button("📥 인사 DB(members.xlsx) 다운로드", f, file_name="members_backup.xlsx")
        
        st.subheader("🚀 민원 카테고리")
        cats = [("🛠️ 시설/수리", "사옥·차량 유지보수, 장비 교체 및 수리 요청"), ("👤 입퇴사/이동", "제증명 발급, 인사 발령, 근무 확인 및 채용"), ("📋 프로세스/규정", "사내 규정 안내, 시스템 이슈 및 보안 문의"), ("🎁 복지/휴가", "경조사, 지원금, 교육 지원 및 동호회 활동"), ("📢 불편사항", "근무 환경 내 불편 및 피해 사항 컴플레인"), ("💬 일반/기타", "단순 질의, 일반 업무 협조 및 기타 문의")]
        
        for title, desc in cats:
            if st.button(f"{title}\n{desc}", key=title, disabled=st.session_state["inquiry_active"]):
                st.session_state["inquiry_active"] = True
                st.session_state.messages.append({"role": "assistant", "content": f"[{title}] 주제에 대해 상담을 시작합니다. 무엇을 도와드릴까요?"})
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.session_state["inquiry_active"]:
            if st.button("✅ 현재 상담 종료하기", use_container_width=True):
                st.session_state["inquiry_active"] = False
                st.session_state["messages"] = []
                st.rerun()
        
        if st.button("🚪 안전하게 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        
        st.markdown("<p class='beta-notice'>※베타 테스트중입니다.<br>오류가 많아도 이해 바랍니다.:)</p>", unsafe_allow_html=True)

    if not st.session_state.messages:
        dynamic_greeting = get_dynamic_greeting()
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']} {user['rank']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{dynamic_greeting}</p></div>", unsafe_allow_html=True)
    
    # [핵심] 대화 기록 렌더링 및 파일 경로 로직 (docs/doa 반영)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                for file_name in RULES_LIST:
                    if file_name in msg["content"]:
                        # 폴더 트리 구조에 따른 경로 자동 분기
                        file_path = f"docs/doa/{file_name}" if file_name.startswith("doa_") else f"docs/{file_name}"
                        if os.path.exists(file_path):
                            with open(file_path, "rb") as f:
                                st.download_button(label=f"📂 {file_name} 다운로드", data=f, file_name=file_name, mime="application/octet-stream", key=f"dl_{file_name}_{msg['content'][:10]}")

    # 채팅 입력 및 답변 생성
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state["inquiry_active"] = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        sys_msg = f"""너는 1990년 창립된 KCIM의 HR팀 팀장이야. {user['name']}님께 정중하고 정확하게 답변해줘.
        [핵심 지침]
        1. 질문자의 의도를 정확하게 파악해주세요. (예: "아픈 부모님 간병" -> "가족돌봄휴가")
        2. 아래 규정 파일 내용을 바탕으로 질문에 대해 '직접적이고 구체적인 답변'을 제공해.
        3. 만약 사내 규정에 없는 '법적 기준'이나 '공식 정보'를 물어본다면, 네가 알고 있는 최신 법령(근로기준법 등)과 공신력 있는 자료를 바탕으로 답변해줘.
        4. 외부 정보를 알려줄 때는 출처를 분명하게 표시해줘.
        5. "파일을 확인해보세요", "파일을 참고하세요"라고 떠넘기지 마세요. 챗봇이 직접 규정 파일 내용을 읽고 문장으로 풀어서 해결책을 제시해줘.
        6. 아는 정보는 즉시 답변하되, 절차에 필요한 '양식 파일명'을 답변에 반드시 포함해.
        7. 자료가 없거나, 답변이 어려운건 솔직하게 "이 부분은 잘 모르겠습니다. 담당자가 확인할 수 있도록 기록하겠습니다."로 답변
        8. 답변 마지막에 관련 자료가 필요한지 물어보고 요청을 한다면 해당 파일 다운로드 버튼을 제시해줘.
        9. 마지막에 [CATEGORY:분류] 필수.
        {COMPANY_DOCUMENTS_INFO}
        
        [원칙]
        1. 시설 수리 등 실무 확인이 필요한 건은 끝에 반드시 [ACTION]을 붙여줘.
        2. 마지막엔 반드시 [CATEGORY:분류명]을 포함해줘.
        """
        
        with st.spinner("HR 챗봇이 내용을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                answer = res.choices[0].message.content
                status = "담당자 확인 필요" if "[ACTION]" in answer else "처리완료"
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "일반/기타"
                clean_ans = answer.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
                
                with st.chat_message("assistant"):
                    st.write(clean_ans)
                    for file_name in RULES_LIST:
                        if file_name in clean_ans:
                            # 답변 생성 시에도 폴더 트리 경로 반영
                            file_path = f"docs/doa/{file_name}" if file_name.startswith("doa_") else f"docs/{file_name}"
                            if os.path.exists(file_path):
                                with open(file_path, "rb") as f:
                                    st.download_button(label=f"📂 {file_name} 다운로드", data=f, file_name=file_name, mime="application/octet-stream", key=f"new_dl_{file_name}")

                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                q_summary = summarize_text(prompt)
                a_summary = summarize_text(clean_ans)
                save_to_sheet(user['dept'], user['name'], user['rank'], category, q_summary, a_summary, status)
                st.rerun() 
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
