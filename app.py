import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# 페이지 설정
st.set_page_config(page_title="더뉴치과 상담일지", layout="wide")
st.title("📝 더뉴치과 상담일지 작성")

# ===== 로그인 =====
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🔐 비밀번호를 입력하세요</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("🔑 비밀번호", type="password", placeholder="비밀번호 입력")
        if st.button("로그인", use_container_width=True):
            if password == "2874":
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 틀렸습니다.")
    st.stop()

# ===== Google Sheets 연결 =====
@st.cache_resource
def get_gsheet_client():
    """Google Sheets 클라이언트 생성"""
    try:
        credentials = st.secrets["connections"]["gsheets"]
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(credentials, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"🚨 Google Sheets 인증 실패: {str(e)}")
        return None

def get_worksheet():
    """워크시트 가져오기"""
    try:
        client = get_gsheet_client()
        if client is None:
            return None
        
        credentials = st.secrets["connections"]["gsheets"]
        spreadsheet_id = credentials["spreadsheet"]
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet("상담일지")
        return worksheet
    except Exception as e:
        st.error(f"🚨 워크시트 연결 실패: {str(e)}")
        return None

# ===== 상담일지 작성 폼 =====
st.header("📋 상담 정보 입력")

col1, col2, col3 = st.columns(3)

with col1:
    input_date = st.date_input("📅 날짜", datetime.now().date())

with col2:
    consultant = st.selectbox("👤 상담자", ["우다혜", "전누리", "임예린"])

with col3:
    doctor = st.selectbox("🩺 진단 원장", ["김동현 원장", "김언형 원장", "정성영 원장", "박경리 원장", "권영은 원장"])

# 중간 섹션
col1, col2, col3 = st.columns(3)

with col1:
    patient_name = st.text_input("👤 환자 성함", placeholder="이름 입력")

with col2:
    chart_no = st.text_input("🔢 차트 번호", placeholder="번호 입력")

with col3:
    category = st.selectbox("📂 분류", ["예약 신청", "상담"])

# 결과 섹션
col1, col2, col3 = st.columns(3)

with col1:
    result = st.selectbox("✅ 상담 결과", ["확정", "미확정"])

with col2:
    amount = st.text_input("💰 금액", placeholder="0", value="0")

with col3:
    points = st.text_input("⭐ 주요 포인트", placeholder="포인트 입력", value="0")

# 상담 내용
content = st.text_area("💬 상담 내용", placeholder="상담 내용을 입력하세요...", height=150)

# ===== 저장 버튼 =====
if st.button("💾 저장하기", use_container_width=True):
    # 필수 필드 검증
    if not patient_name:
        st.error("❌ 환자 성함을 입력해주세요!")
    elif not content:
        st.error("❌ 상담 내용을 입력해주세요!")
    else:
        try:
            worksheet = get_worksheet()
            if worksheet is None:
                st.error("❌ Google Sheets 연결 실패")
            else:
                # 데이터 준비
                new_row = [
                    input_date.strftime("%Y-%m-%d"),
                    consultant,
                    doctor,
                    patient_name,
                    chart_no,
                    category,
                    result,
                    format_amount(amount),
                    points,
                    content,
                    "미리콜"
                ]
                
                # Google Sheets에 행 추가
                worksheet.append_row(new_row)
                
                st.success("✅ 저장되었습니다!")
                st.balloons()
                
                # 저장된 내용 표시
                st.subheader("📝 방금 저장된 내용")
                st.write(f"**날짜:** {input_date}")
                st.write(f"**상담자:** {consultant}")
                st.write(f"**진단 원장:** {doctor}")
                st.write(f"**환자 성함:** {patient_name}")
                st.write(f"**차트 번호:** {chart_no}")
                st.write(f"**분류:** {category}")
                st.write(f"**상담 결과:** {result}")
                st.write(f"**금액:** {format_amount(amount):,}원")
                st.write(f"**주요 포인트:** {points}")
                st.write(f"**상담 내용:** {content}")
                
        except Exception as e:
            st.error(f"🚨 저장 중 에러 발생: {str(e)}")

def format_amount(value):
    """금액을 정수로 변환"""
    try:
        return int(float(value)) if value else 0
    except:
        return 0

# 하단 연결 상태 표시
st.divider()
col1, col2 = st.columns(2)

with col1:
    if st.button("🔍 Google Sheets 연결 확인"):
        try:
            worksheet = get_worksheet()
            if worksheet:
                data = worksheet.get_all_records()
                st.success(f"✅ Google Sheets 연결 성공! (저장된 행: {len(data)}개)")
            else:
                st.error("❌ Google Sheets 연결 실패")
        except Exception as e:
            st.error(f"❌ 연결 확인 실패: {str(e)}")

with col2:
    if st.button("🔓 로그아웃"):
        st.session_state.logged_in = False
        st.rerun()
