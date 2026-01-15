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

# --- UI 고정 및 실시간 시계/여백 최적화 커스텀 CSS ---
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
    
    /* 안내 문구 및 실시간 시계 스타일 */
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 30px; line-height: 1.4; }
    .live-clock-container { font-size: 14px; color: #666; text-align: center; margin-top: 10px; font-weight: 600; font-family: 'Courier New', Courier, monospace; }

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
1. 2025년_복지제도.pdf: 연차, Refresh 휴가, 자녀 학자금 등 복지제도 전반
2. 2025년 달라지는 육아지원제도.pdf: 육아휴직, 단축근무, 정부지원 등
3. 2025_현장근무지원금_최종.pdf: 식대, 교통비, 원거리 지원금 지침
4. 사고발생처리 매뉴얼.pdf: 사고 보고 절차 및 산재처리 프로세스
5. 행동규범.pdf: 임직원 행동 수칙 및 윤리 규정
6. 취업규칙_2025.pdf: 근무시간, 휴가, 복무 등 회사 운영 전반
... (중략) ...
17. 경영관리본부 업무분장표.pdf: 각 본부별 담당업무 분장
"""

# --------------------------------------------------------------------------
# [2] 유틸리티 기능 (KST 보정, 요약, 시트 저장)
# --------------------------------------------------------------------------
def get_kst_now():
    """서버 시간과 관계없이 한국 표준시(KST) 반환"""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst)

def get_dynamic_greeting():
    """KST 기준 시간대별 맞춤형 인사말"""
    now_hour = get_kst_now().hour
    if 5 <= now_hour < 11: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 11 <= now_hour < 14: return "즐거운 점심시간입니다. 맛있는 식사 하셨나요? 🍱"
    elif 14 <= now_hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    elif 18 <= now_hour < 22: return "오늘 하루도 고생 많으셨습니다! 마무리하며 도와드릴 일이 있을까요? ✨"
    else: return "늦은 시간까지 수고가 많으시네요. 무엇을 도와드릴까요? 🌙"

def summarize_text(text):
    """시트 기록용 핵심 요약"""
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "1문장 요약해줘."}], temperature=0)
        return res.choices[0].message.content.strip()
    except: return text[:30] + "..."

def save_to_sheet(dept, name, rank, category, question, answer, status):
    """구글 시트 실시간 저장"""
    sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit#gid=1434430603"
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_sheets"]), ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        sheet = gspread.authorize(creds).open_by_url(sheet_url).worksheet("응답시트")
        current_time = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([current_time, dept, name, rank, category, question, answer, status])
    except: pass

# --------------------------------------------------------------------------
# [3] 데이터 로드 (KCIM 1990년 창립 및 인사 데이터)
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
                db[name] = {"pw": str(row['휴대폰 번호'])[-4:], "dept": str(row['부서']).strip(), "rank": str(row['직급']).strip()}
        except: pass
    return db

EMPLOYEE_DB = load_employee_db()

# --------------------------------------------------------------------------
# [4] 메인 UI 실행
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

if not st.session_state["logged_in"]:
    # 로그인 폼 생략 (기존과 동일)
    pass 

else:
    user = st.session_state["user_info"]
    with st.sidebar:
        # 1. 로고 (가운데 정렬)
        st.markdown("<div style='text-align: center; width: 100%;'><h2 style='color: #1a1c1e; margin-bottom: 20px;'>🏢 KCIM</h2></div>", unsafe_allow_html=True)
        
        # 2. 사용자 정보 (HR팀 표기)
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>{user['dept']}</span></div>", unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        # 3. 카테고리 버튼
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
        
        # 4. 로그아웃 버튼
        if st.button("🚪 안전하게 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        
        # 5. 베타 안내 및 [요청사항] 실시간 KST 라이브 클락 (hh:mm:ss)
        # 자바스크립트를 삽입하여 초 단위로 움직이는 시계를 구현합니다.
        st.markdown(f"""
            <p class='beta-notice'>이 챗봇은 현재 베타테스트중입니다.<br>오류가 나도 이해해주세요:)</p>
            <div id="live-clock" class="live-clock-container">KST 00:00:00</div>
            
            <script>
            function updateClock() {{
                const now = new Date();
                // KST 보정 (UTC+9)
                const kstOffset = 9 * 60 * 60 * 1000;
                const kstDate = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + kstOffset);
                
                const hours = String(kstDate.getHours()).padStart(2, '0');
                const minutes = String(kstDate.getMinutes()).padStart(2, '0');
                const seconds = String(kstDate.getSeconds()).padStart(2, '0');
                
                document.getElementById('live-clock').innerHTML = "KST " + hours + ":" + minutes + ":" + seconds;
            }}
            setInterval(updateClock, 1000);
            updateClock(); // 즉시 실행
            </script>
        """, unsafe_allow_html=True)

    # 6. 메인 화면 (인사말 및 채팅 로직은 기존과 동일)
    if not st.session_state.messages:
        dynamic_greeting = get_dynamic_greeting()
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']} {user['rank']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{dynamic_greeting}</p></div>", unsafe_allow_html=True)
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    if prompt := st.chat_input("문의 내용을 입력하세요"):
        # 답변 로직 생략 (기존 17종 규정 참조 로직 유지)
        pass
