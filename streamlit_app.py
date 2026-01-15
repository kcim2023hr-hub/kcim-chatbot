import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import traceback
import time

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 직원 명단 (성명과 사번만 일치하면 접속 허용)
# 형식: "이름": "사번(비밀번호)" -> 실제 사용하실 때 이 부분을 수정하세요.
# --------------------------------------------------------------------------
ALLOWED_USERS = {
    "관리자": "1234",
    "홍길동": "240101",
    "김철수": "240102",
    "이영희": "240103"
}

# --------------------------------------------------------------------------
# [2] 구글 시트 주소 (보내주신 주소를 적용했습니다!)
# --------------------------------------------------------------------------
sheet_url = "https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit?gid=1434430603#gid=1434430603"

# 2. 비밀번호(Secrets) 불러오기
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error(f"비밀번호 설정 오류: {e}")
    st.stop()

# 3. 구글 시트 연결 및 저장 함수 (정보 3개 모두 저장)
def save_to_sheet(dept, name, rank, question, answer):
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gs_client = gspread.authorize(creds)
        
        # 시트 열기 (탭 이름이 '응답시트'여야 합니다)
        sheet = gs_client.open_by_url(sheet_url).worksheet("응답시트")
        
        # 날짜 기록
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # [기록 순서] 부서, 성명, 직급을 순서대로 저장
        # 엑셀 헤더 순서: [날짜, 부서, 성명, 직급, 질문, 답변, 비고]
        sheet.append_row([now, dept, name, rank,
