import streamlit as st
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
import os
import re

# 1. 페이지 설정
st.set_page_config(page_title="KCIM 민원 챗봇", page_icon="🏢")
st.title("🤖 KCIM 사내 민원/문의 챗봇")

# --------------------------------------------------------------------------
# [1] 데이터 로드 (임직원 정보 및 업무 분장)
# --------------------------------------------------------------------------

@st.cache_data
def load_employee_db():
    file_name = 'members.xlsx' 
    db = {}
    db["관리자"] = {"pw": "1323", "dept": "HR팀", "rank": "매니저"}
    if os.path.exists(file_name):
        try:
            df = pd.read_excel(file_name, engine='openpyxl')
            df.columns = [str(c).strip() for c in df.columns]
            for _, row in df.iterrows():
                try:
                    name = str(row['이름']).strip()
                    phone = str(row['휴대폰 번호']).strip()
                    pw = re.sub(r'[^0-9]', '', phone)[-4:]
                    db[name] = {"pw": pw, "dept": row['부서'], "rank": row['직급']}
                except:
                    continue
        except:
            pass
    return db

EMPLOYEE_DB = load_employee_db()

# 업무 분장표 데이터
WORK_DISTRIBUTION = """
[KCIM 경영관리본부 업무 분장표]
- 이경한 매니저: 시설 관리(사옥/법인차량), 숙소 관리(계약/관리/종료), 근태 관리(지각/연차/휴가), 행사 기획/실행, 제증명 발급(재직/퇴직/경력), 출장(쏘카/숙박), 현장 관리 등
- 김병찬 매니저: 제도 공지, 취업규칙, 평가보상, 계약서 검토
- 백다영 매니저: 교육(리더/법정), 채용(공고/면접), 입퇴사 안내, 양식 변경
- 김승민 매니저: 품의서 관리, 비용 처리(법인카드), 지출결의서, 신용평가서
- 안하련 매니저: 급여 서류(원천징수영수증), 품의 금액 송금
- 손경숙 매니저: 비품 구매
- 최관식 매니저: 내부 직원 정보 관리 (어울지기, 플로우)
"""

# --------------------------------------------------------------------------
# [2] 외부 서비스 설정 (OpenAI & 구글 시트)
# --------------------------------------------------------------------------
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    google_secrets = st.secrets["google_sheets"]
except Exception as e:
    st.error("⚠️ Secrets 설정 오류가 발생했습니다.")
    st.stop()

def save_to_sheet(dept, name, rank, category, question, answer):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(google_secrets), scope)
        gc = gspread.authorize(creds)
        # 구글 시트 URL
        sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1jckiUzmefqE_PiaSLVHF2kj2vFOIItc3K86_1HPWr_4/edit")
        sheet = sh.worksheet("응답시트")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, dept, name, rank, category, question, answer])
    except:
        pass

# --------------------------------------------------------------------------
# [3] UI 및 메인 로직
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.header("🔒 임직원 신원확인")
    with st.form("login_form"):
        name = st.text_input("성명")
        pw = st.text_input("비밀번호 (휴대폰 뒷 4자리)", type="password")
        if st.form_submit_button("접속하기"):
            if name in EMPLOYEE_DB and EMPLOYEE_DB[name]["pw"] == pw:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = EMPLOYEE_DB[name]
                st.session_state["user_info"]["name"] = name
                st.rerun()
            else:
                st.error("정보가 일치하지 않습니다.")
else:
    user = st.session_state["user_info"]
    with st.sidebar:
        st.markdown(f"👤 **{user['name']} {user['rank']}**")
        st.caption(f"🏢 {user['dept']}")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": f"반갑습니다 {user['name']}님! 😊 무엇을 도와드릴까요?"}]

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # 시스템 지침 (성함 언급 지양 및 정중한 표현)
        sys_instr = f"""너는 KCIM의 HR AI 매니저야.
        1. 상담 안내 번호는 02-772-5806으로 안내해.
        2. 답변 시 특정 담당자를 지칭할 때는 반드시 'OOO 매니저'라고 정중히 표현해.
        3. 아래 [업무 분장표]를 참고해서 담당자를 안내해줘:
        {WORK_DISTRIBUTION}
        4. 이경한 매니저의 담당 업무라면 'HR팀 이경한 매니저에게 문의바랍니다.'라고 안내해.
        5. 답변 마지막에 [CATEGORY:분류] 태그를 달아줘. (분류: 인사, 복지, 시설, 기타 중 선택)
        """
        
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_instr}, {"role": "user", "content": prompt}])
        ans = response.choices[0].message.content
        
        # 카테고리 추출 및 시트 기록
        cat_match = re.search(r'\[CATEGORY:(.*?)\]', ans)
        cat_str = cat_match.group(1) if cat_match else "기타"
        save_to_sheet(user['dept'], user['name'], user['rank'], cat_str, prompt, ans)

        st.session_state.messages.append({"role": "assistant", "content": ans})
        st.chat_message("assistant").write(ans)
