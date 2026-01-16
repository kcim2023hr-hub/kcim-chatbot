import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
import re
import requests  # [필수] 플로우 API 호출용

# --------------------------------------------------------------------------
# [1] 페이지 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢", layout="centered")

# --------------------------------------------------------------------------
# [2] UI 커스텀 CSS (디자인 최적화 적용)
# --------------------------------------------------------------------------
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .block-container { max-width: 800px !important; padding-top: 5rem !important; }
    
    /* 로그인 폼 스타일 */
    div[data-testid="stForm"] { background-color: #ffffff; padding: 50px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; text-align: center; }
    div[data-testid="stNotification"] { font-size: 16px; background-color: #f0f7ff; border-radius: 12px; color: #0056b3; padding: 20px; }
    
    /* 사이드바 스타일 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #dee2e6; }
    div[data-testid="stSidebar"] .stButton > button { background-color: #ffffff !important; border: 1px solid #e9ecef !important; padding: 15px 10px !important; border-radius: 12px !important; width: 100% !important; margin-bottom: 2px !important; }
    div[data-testid="stSidebar"] .stButton > button p { font-size: 14px !important; color: #495057 !important; font-weight: 600 !important; }
    
    .beta-notice { font-size: 12px; color: #999; text-align: center; margin-top: 60px !important; line-height: 1.6; }
    .greeting-container { text-align: center; margin-bottom: 45px; padding: 25px 0; }
    .greeting-title { font-size: 38px !important; font-weight: 800; color: #1a1c1e; margin-bottom: 15px; }
    .greeting-subtitle { font-size: 21px !important; color: #555; }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# [3] 플로우(Flow) 데이터 실시간 연동 함수
# --------------------------------------------------------------------------
@st.cache_data(ttl=600)  # 10분마다 데이터 갱신
def fetch_flow_data():
    # secrets에 키가 없으면 빈 문자열 반환 (오류 방지)
    if "flow_api" not in st.secrets:
        return ""
    
    api_key = st.secrets["flow_api"]["api_key"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # ※ 중요: 플로우 API 문서를 확인하여 정확한 Endpoint를 입력하세요.
    # 일반적인 Open API 주소 예시입니다. (https://openapi.flow.team 등)
    base_url = "https://openapi.flow.team/v1" 
    target_projects = ["[KCIM] 전체 공지사항", "[경영본부] HR팀"]
    collected_text = ""

    try:
        # 1. 프로젝트 목록 조회
        # (만약 API 주소가 다르면 이곳을 수정해야 합니다)
        res = requests.get(f"{base_url}/projects", headers=headers, timeout=5)
        
        if res.status_code == 200:
            projects = res.json().get("result", []) # 응답 구조가 {'result': [...]} 라고 가정
            
            for t_title in target_projects:
                # 제목이 일치하는 프로젝트 ID 찾기
                p_id = next((p['id'] for p in projects if p.get('title') == t_title), None)
                
                if p_id:
                    # 2. 게시글 조회
                    post_res = requests.get(f"{base_url}/projects/{p_id}/posts", headers=headers, timeout=5)
                    if post_res.status_code == 200:
                        posts = post_res.json().get("result", [])
                        collected_text += f"\n\n[Flow 공지: {t_title}]\n"
                        # 최신글 3개만 요약해서 가져오기
                        for post in posts[:3]:
                            title = post.get('title', '제목 없음')
                            content = post.get('contents', '')[:100].replace('\n', ' ') # 본문 100자 제한
                            collected_text += f"- {title}: {content}...\n"
    except Exception:
        # API 연결 실패 시 챗봇이 멈추지 않도록 조용히 패스
        pass
        
    return collected_text

# --------------------------------------------------------------------------
# [4] 지식 베이스 (고정 규정 + Flow 실시간 데이터)
# --------------------------------------------------------------------------
# Flow 데이터 가져오기
flow_realtime_info = fetch_flow_data()

STATIC_DOCS = """
[KCIM HR 규정 및 양식 핵심 가이드]
※ 챗봇 답변의 근거 자료입니다.

1. [휴가 및 복지]
   - **배우자 출산 휴가**: 법적 기준에 따라 '유급 20일' 부여 (최우선 답변). 필요시 'KCIM_가족돌봄 휴가신청서.xlsx' 사용 안내.
   - **가족돌봄휴가**: 가족의 질병/사고/노령 등으로 사용. 연간 최장 90일(무급). 양식: 'KCIM_가족돌봄 휴가신청서.xlsx'
   - **난임치료휴가**: 연간 3일(최초 1일 유급). 양식: 'KCIM_난임치료휴가 신청서.xlsx'
   - **성장포인트**: 자기개발/도서구입 등 사용. 양식: 'KCIM_성장포인트 적립 및 사용 신청서.xlsx'
   - **자녀 학자금**: 고/대 자녀 학비 지원 (상세: 2026년_복지제도.pdf).

2. [근무 및 행정]
   - **재택근무**: 부서장 승인 필요, 주 1~2회. 규정: '2024_재택근무_운영규정(최종본).pdf'
   - **법인차량**: 반납/인계 시 'KCIM_법인차량_인수인계서.xlsx' 필수. 사고 시 'KCIM_사고경위서.xlsx'.
   - **명함 신청**: 'KCIM_명함신청양식.xlsx' 작성 후 경영지원팀 제출.
   - **기안서**: 비용 발생/대외 공문 전 내부 승인. 양식: 'KCIM_기안서.xlsx'

3. [프로젝트 및 계약]
   - **BIM 프로젝트 종료**: 산출물/이슈 보고. 양식: 'KCIM_BIM 프로젝트 종료 프로세스 & 결과 보고서.xlsx'
   - **업무 인수인계**: 필수 작성. 양식: 'KCIM_BIM 프로젝트 업무 인수인계서.xlsx'
   - **계약서**: 도급('도급인기준.docx'), 수급('수급인기준.docx') 사용.

4. [인사 명령/이동]
   - **부서 이동**: 'KCIM_부서이동요청서.xlsx' 작성.
   - **겸직 허가**: 영리 활동 시 사전 승인. 'KCIM_겸직허가신청서.xlsx'.
   - **사직/복직**: 퇴사 30일 전(사직서), 복귀 시(복직원).

[답변 지침]
- 위 규정과 아래 [Flow 실시간 공지] 내용을 종합하여 답변하세요.
- 파일명(KCIM_...)이 있으면 반드시 언급하세요.
"""

# 최종 지식 합체
COMPANY_DOCUMENTS_INFO = STATIC_DOCS + flow_realtime_info

RULES_LIST = [
    "2026년_복지제도.pdf", "2025년 달라지는 육아지원제도(고용노동부).pdf", "취업규칙(2025년)_케이씨아이엠.pdf",
    "doa_0_overview.pdf", "doa_1_common.pdf", "doa_2_management.pdf", "doa_3_system.pdf",
    "doa_4_hr.pdf", "doa_5_tech.pdf", "doa_6_strategy.pdf", "doa_7_cx.pdf", "doa_8_solution.pdf",
    "doa_9_hitech.pdf", "doa_10_bim.pdf", "doa_11_ts.pdf", "doa_12_consulting.pdf",
    "2024_재택근무_운영규정(최종본).pdf", "[KCIM] 계약서 검토 프로세스 안내.pdf", "사업자등록증(KCIM).pdf",
    "사고발생처리 매뉴얼(2023년).pdf", "[사내 와이파이(Wifi) 정보 및 비밀번호].txt", "[경영관리본부 업무 분장표].txt",
    "KCIM BIM용역 계약서_도급인기준.docx", "KCIM BIM용역 계약서_수급인기준.docx", "KCIM_BIM 프로젝트 업무 인수인계서.xlsx",
    "KCIM_BIM 프로젝트 종료 프로세스 & 결과 보고서.xlsx", "KCIM_가족돌봄 휴가신청서.xlsx", "KCIM_겸직허가신청서.
