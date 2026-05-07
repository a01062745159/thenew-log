import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="더뉴치과 상담일지", layout="wide")
st.title("📝 상담일지 입력")

# Google Sheets 연결
def get_worksheet():
    try:
        credentials = st.secrets["connections"]["gsheets"]
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(credentials, scopes=scopes)
        client = gspread.authorize(creds)
        
        spreadsheet_id = credentials["spreadsheet"]
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet("상담일지")
        return worksheet
    except Exception as e:
        st.error(f"🚨 연결 에러: {str(e)}")
        return None

# 입력 폼
st.header("상담 정보 입력")

col1, col2, col3 = st.columns(3)
with col1:
    date = st.date_input("📅 날짜", datetime.now().date())
with col2:
    consultant = st.text_input("👤 상담자", placeholder="우다혜")
with col3:
    doctor = st.text_input("🩺 진단원장", placeholder="김동현 원장")

col1, col2, col3 = st.columns(3)
with col1:
    patient_name = st.text_input("👤 환자성함", placeholder="이름")
with col2:
    chart_no = st.text_input("🔢 차트번호", placeholder="12345")
with col3:
    category = st.text_input("📂 분류", placeholder="예약 신청")

col1, col2, col3 = st.columns(3)
with col1:
    result = st.text_input("✅ 상담결과", placeholder="확정/미확정")
with col2:
    amount = st.text_input("💰 금액", placeholder="0")
with col3:
    main_point = st.text_input("⭐ 주요포인트", placeholder="포인트")

content = st.text_area("💬 상담내용", placeholder="상담 내용 입력", height=150)
recall_status = st.text_input("🔄 리콜상태", placeholder="미리콜")

# 저장 버튼
if st.button("💾 저장", use_container_width=True):
    if not patient_name or not content:
        st.error("❌ 환자성함과 상담내용은 필수입니다!")
    else:
        worksheet = get_worksheet()
        if worksheet:
            try:
                # 데이터 준비
                row = [
                    date.strftime("%Y-%m-%d"),
                    consultant,
                    doctor,
                    patient_name,
                    chart_no,
                    category,
                    result,
                    amount,
                    main_point,
                    content,
                    recall_status
                ]
                
                # 저장
                worksheet.append_row(row)
                st.success("✅ 저장되었습니다!")
                st.balloons()
                
            except Exception as e:
                st.error(f"❌ 저장 실패: {str(e)}")
