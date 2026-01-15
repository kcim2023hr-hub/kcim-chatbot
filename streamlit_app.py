import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
import re

# 1. 페이지 설정: 중앙 정렬 레이아웃 고정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --- UI 고정 커스텀 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }
    div[data-testid="stForm"] { background-color: #ffffff; padding: 50px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; text-align: center; }
    div[data-testid="stNotification"] { font-size: 16px; background-color: #f0f7ff; border-radius: 12px; color: #0056b3; padding: 20px; }
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    .sidebar-user-box { background-color: #f8f9fa; padding: 20px; border-radius: 15px; border: 1px solid #edf0f2; margin-bottom: 20px; text-align: center; }
    
    /* 로고 중앙 정렬 */
    div[data-testid="stSidebar"] .stButton > button { background-color: #ffffff !important; border: 1px solid #e9ecef !important; padding: 18px 15px !important; border-radius: 15px !important; width: 100% !important; margin-bottom: -5px !important; }
    
    /* 베타 테스트 안내 문구 여백 */
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 60px !important; line-height: 1.6; }

    /* 중앙 플랫 인사말 */
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 21px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [1] 규정 파일 지식 베이스 및 다운로드 매핑
# --------------------------------------------------------------------------
# GitHub 'rules' 폴더에 저장될 파일 리스트
RULES_LIST = [
    "2025년_복지제도.pdf", "2025년 달라지는 육아지원제도.pdf", "2025_현장근무지원금_최종.pdf",
    "사고발생처리 매뉴얼.pdf", "행동규범.pdf", "취업규칙_2025.pdf", "노동부 지원금 매뉴얼.pdf",
    "KCIM 계약서 검토 프로세스.pdf", "2024 재택근무 내부프로세스.pdf", "2024_재택근무_운영규정.pdf",
    "연차유예 및 대체휴가 지침.pdf", "임직원 연락망_2025.pdf", "도서구입 및 도서관 운영지침.docx",
    "사내동호회운영규정.pdf", "사내 와이파이 정보.pdf", "2023_KCIM_사내도서지원.pptx",
    "경영관리본부 업무분장표.pdf"
]

# --------------------------------------------------------------------------
# [2] 유틸리티 기능 (인사말, 요약, 시트 저장 등)
# --------------------------------------------------------------------------
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def get_dynamic_greeting():
    """시간대별 인사말 복구"""
    now_hour = get_kst_now().hour
    if 5 <= now_hour < 11: return "좋은 아침입니다! 오늘도 활기차게 시작해볼까요? ☀️"
    elif 11 <= now_hour < 14: return "즐거운 점심시간입니다. 맛있는 식사 하셨나요? 🍱"
    elif 14 <= now_hour < 18: return "즐거운 오후입니다. 업무 중에 궁금한 점이 있으신가요? ☕"
    elif 18 <= now_hour < 22: return "오늘 하루도 고생 많으셨습니다! 마무리하며 도와드릴 일이 있을까요? ✨"
    else: return "늦은 시간까지 수고가 많으시네요. 무엇을 도와드릴까요? 🌙"

def summarize_text(text):
    """시트 요약 기록 복구"""
    if not text: return "-"
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "15자 이내로 핵심만 요약해."}, {"role": "user", "content": text}],
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
# [3] UI 및 대화 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "messages" not in st.session_state: st.session_state["messages"] = []
if "inquiry_active" not in st.session_state: st.session_state["inquiry_active"] = False

# [로그인 로직 생략 - 기존과 동일]
if not st.session_state["logged_in"]:
    # ... (생략) ...
    pass

else:
    user = st.session_state["user_info"]
    with st.sidebar:
        # 로고 중앙 정렬
        st.markdown("<div style='text-align: center; width: 100%;'><h2 style='color: #1a1c1e; margin-bottom: 20px;'>🏢 KCIM</h2></div>", unsafe_allow_html=True)
        # HR팀 명칭 반영
        st.markdown(f"<div class='sidebar-user-box'><small>인증된 사용자</small><br><b style='font-size: 20px;'>{user['name']} {user['rank']}</b><br><span style='color: #28a745; font-weight: 600;'>HR팀</span></div>", unsafe_allow_html=True)
        
        st.subheader("🚀 민원 카테고리")
        # 카테고리 및 로그아웃 여백 유지
        # ... (카테고리 버튼 생성 로직 생략) ...
        
        st.markdown("<p class='beta-notice'>이 챗봇은 현재 베타테스트중입니다.<br>오류가 나도 이해해주세요:)</p>", unsafe_allow_html=True)

    # 메인 인사말 복구
    if not st.session_state.messages:
        dynamic_greeting = get_dynamic_greeting()
        st.markdown(f"<div class='greeting-container'><p class='greeting-title'>{user['name']} {user['rank']}님, 반갑습니다! 👋</p><p class='greeting-subtitle'>{dynamic_greeting}</p></div>", unsafe_allow_html=True)
    
    # 대화 기록 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            # 답변에 파일명이 포함되어 있다면 다운로드 버튼 출력
            if msg["role"] == "assistant":
                for file_name in RULES_LIST:
                    if file_name in msg["content"]:
                        file_path = f"rules/{file_name}"
                        if os.path.exists(file_path):
                            with open(file_path, "rb") as f:
                                st.download_button(label=f"📂 {file_name} 다운로드", data=f, file_name=file_name, mime="application/octet-stream")

    # 채팅 입력 및 처리
    if prompt := st.chat_input("문의 내용을 입력하세요"):
        st.session_state["inquiry_active"] = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        # 시스템 지침에 파일 목록 재강조
        sys_msg = f"너는 1990년 창립된 KCIM의 HR팀 매니저야. 아래 파일 목록 중 관련 있는 파일명을 답변에 포함해줘: {', '.join(RULES_LIST)}"
        
        with st.spinner("KCIM 매니저가 규정을 확인 중입니다..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages)
                answer = res.choices[0].message.content
                
                # 가공 및 화면 표시
                status = "담당자 확인 필요" if "[ACTION]" in answer else "처리완료"
                category = re.search(r'\[CATEGORY:(.*?)\]', answer).group(1) if "[CATEGORY:" in answer else "일반/기타"
                clean_ans = answer.replace("[ACTION]", "").replace(f"[CATEGORY:{category}]", "").strip()
                
                with st.chat_message("assistant"):
                    st.write(clean_ans)
                    # 신규 답변에서도 즉시 다운로드 버튼 표시
                    for file_name in RULES_LIST:
                        if file_name in clean_ans:
                            file_path = f"rules/{file_name}"
                            if os.path.exists(file_path):
                                with open(file_path, "rb") as f:
                                    st.download_button(label=f"📂 {file_name} 다운로드", data=f, file_name=file_name, mime="application/octet-stream")
                
                st.session_state.messages.append({"role": "assistant", "content": clean_ans})
                save_to_sheet(user['dept'], user['name'], user['rank'], category, summarize_text(prompt), summarize_text(clean_ans), status)
                st.rerun() 
            except: pass
