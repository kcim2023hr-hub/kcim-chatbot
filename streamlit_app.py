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
    
    /* 안내 문구 및 시간 표시 스타일 */
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 30px; line-height: 1.4; }
    .time-display { font-size: 11px; color: #bbb; text-align: center; margin-top: 10px; font-family: monospace; }

    /* 중앙 플랫 인사말 디자인 */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 23px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 규정 파일 지식 베이스 맵핑
# --------------------------------------------------------------------------
COMPANY_DOCUMENTS_INFO = """
[KCIM 최신 사내 규정 파일 지식]
1. 2025년_복지제도.pdf: 연차, Refresh 휴가, 자녀 학자금 등 전반
2. 2025년 달라지는 육아지원제도.pdf: 육아휴직, 단축근무, 모성보호 등
3. 2025_현장근무지원금_최종.pdf: 식대, 교통비, 출장, 원거리 지원금
4. 사고발생처리 매뉴얼.pdf: 사고 보고 절차, 산재처리, 민원대응
5. 행동규범.pdf: 윤리 규정, 임직원 행동 수칙 및 위반 시 처리
6. 취업규칙_2025.pdf: 근무시간, 휴가, 복무, 징계 등 전반 규칙
7. 노동부 지원금 매뉴얼.pdf: 청년고용, 출산육아 정부지원 신청 방법
8. KCIM 계약서 검토 프로세스.pdf: 계약서 작성/검토 절차 및 법무검토
9. 2024 재택근무 내부프로세스.pdf: 재택근무 신청 절차 및 근태 기록
10. 2024_재택근무_운영규정.pdf: 재택 운영 지침 및 예외 사항
11. 연차유예 및 대체휴가 지침.pdf: 연차이월, 소진기한, 대체휴가 처리
12. 임직원 연락망_2025.pdf: 부서별 담당자 및 소속 연락처 정보
13. 도서구입 및 도서관 운영지침.docx: 도서 신청, 사내 지식경영 절차
14. 사내동호회운영규정.pdf: 동호회 창설, 운영비 지원, 승인 절차
15. 사내 와이파이 정보.pdf: 층별 SSID 및 비밀번호 안내
16. 2023_KCIM_사내도서지원.pptx: 사내 도서 지원 제도 홍보 및 안내
17. 경영관리본부 업무분장표.pdf: 본부별 담당 직무 및 부서 역할
"""

# --------------------------------------------------------------------------
# [2] 유틸리티 기능 (KST 보정, 요약, 시트 저장)
# --------------------------------------------------------------------------
def get_kst_now():
    """서버 시간과 관계없이 한국 표준시(KST) 반환"""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst)

def get_dynamic_greeting():
    """KST 기준 시간대별 맞춤형 인사말 생성"""
    now_hour = get_kst_now().hour
    if 5 <= now_hour < 11: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 11 <= now_hour < 14: return "즐거운 점심시간입니다. 맛있는 식사 하셨나요? 🍱"
    elif 14 <= now_hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    elif 18 <= now_hour < 22: return "오늘 하루도 고생 많으셨습니다! 마무리하며 도와드릴 일이 있을까요? ✨"
    else: return "늦은 시간까지 수고가 많으시네요. 무엇을 도와드릴까요? 🌙"

def summarize_text(text):
    """구글 시트 기록용 핵심 요약"""
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "1문장으로 아주 짧게 요약해."}, {"role": "user", "content": text}],
            temperature=0
        )
        return res.choices[0].message.content.strip()
    except: return text[:30] + "..."

def save_to_sheet(dept, name, rank, category, question, answer, status):
    """구글 시트 실시간 저장"""
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            dict(st.secrets["google_sheets"]), 
            ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        )
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("응답시트")
        current_time = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([current_time, dept, name, rank, category, question, answer, status])
    except: pass

# --------------------------------------------------------------------------
# [3] 데이터 로드 (KCIM 1990년 창립 반영)
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
                phone = re.sub(r'[^0-9]', '', str(row['휴대폰 번호']))
                db[name] = {"pw": phone[-4:] if len(phone)>=4 else "0000", 
                            "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
            if "이경한" in db: db["이경한"]["pw"] = "1323"
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [4] UI 실행 및 사이드바 구성
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

# [로그인 화면]
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

# [챗봇 메인 화면]
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        # 로고 중앙 정렬
        st.markdown("<div style='text-align: center; width: 100%;'><h2 style='color: #1a1c1e; margin-bottom: 20px;'>🏢 KCIM</h2></div>", unsafe_allow_html=True)
        
        # 사용자 정보 (HR팀 명칭 고정)
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>{user['dept']}</span></div>", unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        # 민원 분류 이미지 내용 반영
        cats = [("🛠️ 시설/수리", "사옥·차량 유지보수, 장비 교체 및 수리 요청"), ("👤 입퇴사/이동", "제증명 발급, 인사 발령, 근무 확인 및 채용"), ("📋 프로세스/규정", "사내 규정 안내, 시스템 이슈 및 보안 문의"), ("🎁 복지/휴가", "경조사, 지원금, 교육 지원 및 동호회 활동"), ("📢 불편사항", "근무 환경 내 불편 및 피해 사항 컴플레인"), ("💬 일반/기타", "단순 질의, 일반 업무 협조 및 기타 문의")]
        
        for title, desc in cats:
            if st.button(f"{title}\n{desc}", key=title, disabled=st.session_state["inquiry_active"]):
                st.session_state["inquiry_active"] = True
                st.session_state.messages.append({"role": "assistant", "content": f"[{title}] 주제에 대해 상담을 시작합니다. 무엇을 도와드릴까요?"})
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True) # 카테고리와 버튼 사이 간격 유지
        
        if st.session_state["inquiry_active"]:
            if st.button("✅ 현재 상담 종료하기", use_container_width=True):
                st.session_state["inquiry_active"] = False
                st.session_state["messages"] = []
                st.rerun()
        
        # [요청사항] 안전하게 로그아웃 버튼 배치
        if st.button("🚪 안전하게 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        
        # [요청사항] 버튼 아래 간격 띄우고 베타 안내 및 현재 시간 장치 추가
        kst_now = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
        st.markdown(f"""
            <p class='beta-notice'> ※ 이 챗봇은 현재 베타테스트중입니다.<br>오류가 많아도 이해 바랍니다:)</p>
            <p class='time-display'>KST 접속 시간: {kst_now}</p>
        """, unsafe_allow_html=True)

    # 메인 인삿말 (플랫 디자인 유지)
    if not st.session_state.messages:
        dynamic_greeting = get_dynamic_greeting()
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']} {user['rank']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{dynamic_greeting}</p></div>", unsafe_allow_html=True)
    
    # 대화 기록 렌더링
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    # 채팅 입력 및 답변 생성 (17종 규정 지식 베이스 활용)
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state["inquiry_active"] = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        sys_msg = f"""너는 1990년 창립된 KCIM의 HR팀 팀장이야. {user['name']}님께 정중히 답변해줘.
        아래의 최신 사내 규정 파일 목록을 정확히 참고하여 답변하고, 근거가 되는 파일명을 언급해줘:
        {COMPANY_DOCUMENTS_INFO}
        
        [원칙]
        1. 시설 수리, 법인 차량, 숙소 예약 등 이경한 매니저의 실무 확인이 필요한 건은 끝에 반드시 [ACTION]을 붙여줘.
        2. 마지막엔 반드시 [CATEGORY:분류명]을 포함해줘.
        """
        
        with st.spinner("KCIM 매니저가 규정을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                answer = res.choices[0].message.content
                
                # 분류 및 요약 가공
                status = "담당자 확인 필요" if "[ACTION]" in answer else "처리완료"
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "일반/기타"
                clean_ans = answer.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
                
                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                
                # 시트 실시간 요약 저장 (KST 기준)
                save_to_sheet(user['dept'], user['name'], user['rank'], category, summarize_text(prompt), summarize_text(clean_ans), status)
                
                st.rerun() 
            except: pass
