import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import matplotlib.pyplot as plt
import matplotlib
from io import BytesIO
import zipfile
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="더뉴치과 상담일지", layout="wide")

# 스타일 설정
st.markdown("""
    <style>
    [data-testid="stDataFrame"] {
        font-size: 14px !important;
    }
    [data-testid="stDataFrame"] tbody tr {
        height: auto !important;
    }
    [data-testid="stDataFrame"] td {
        white-space: normal !important;
        word-break: break-word !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        max-width: 400px !important;
    }
    </style>
""", unsafe_allow_html=True)

# ===== 📋 Helper Functions (반복 코드 제거) =====
def format_amount(value):
    """금액을 정수로 변환"""
    try:
        return int(float(value)) if pd.notnull(value) else 0
    except:
        return 0

def format_chart_no(value):
    """차트번호 포맷팅"""
    try:
        return str(int(float(value))) if pd.notnull(value) and str(value).strip() != '' else ""
    except:
        return ""

def filter_by_date_range(df, start_date, end_date):
    """날짜 범위로 데이터 필터링"""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    return df[(df['날짜'] >= start_str) & (df['날짜'] <= end_str)].copy()

def load_gsheet_data():
    """Google Sheet에서 데이터 로드 (gspread 사용)"""
    try:
        # Streamlit secrets에서 credentials 로드
        credentials = st.secrets["connections"]["gsheets"]
        
        # Google Sheets API 인증
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(credentials, scopes=scopes)
        client = gspread.authorize(creds)
        
        # Google Sheet 열기 (spreadsheet ID 사용)
        spreadsheet_id = credentials["spreadsheet"]
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # "상담일지" 시트 가져오기
        worksheet = spreadsheet.worksheet("상담일지")
        
        # 데이터를 DataFrame으로 변환
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 필수 컬럼 확인 및 추가
        if len(df) > 0:
            # 빈 행 제거 (모든 컬럼이 빈 경우만)
            df = df.dropna(how='all')
        
        # 컬럼 추가
        if '진단원장' not in df.columns:
            df['진단원장'] = ''
        if '리콜상태' not in df.columns:
            df['리콜상태'] = '미리콜'
        
        return df
    except Exception as e:
        st.error(f"🚨 Google Sheets 연결 에러: {str(e)}")
        return pd.DataFrame()

def save_to_gsheet(df):
    """Google Sheet에 데이터 저장"""
    try:
        credentials = st.secrets["connections"]["gsheets"]
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(credentials, scopes=scopes)
        client = gspread.authorize(creds)
        
        spreadsheet_id = credentials["spreadsheet"]
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet("상담일지")
        
        # 기존 데이터 모두 삭제
        worksheet.clear()
        
        # 헤더 추가
        headers = df.columns.tolist()
        worksheet.append_row(headers)
        
        # 데이터 추가
        data_values = df.values.tolist()
        worksheet.append_rows(data_values)
        
        return True
    except Exception as e:
        st.error(f"🚨 저장 에러: {str(e)}")
        return False

def calculate_stats(df):
    """통계 계산"""
    df['금액_숫자'] = pd.to_numeric(df['금액'], errors='coerce').fillna(0)
    
    total_count = len(df)
    total_amount = int(df['금액_숫자'].sum())
    confirmed_count = len(df[df['상담결과'] == '확정'])
    unconfirmed_count = len(df[df['상담결과'] == '미확정'])
    confirmed_amount = int(df[df['상담결과'] == '확정']['금액_숫자'].sum())
    unconfirmed_amount = int(df[df['상담결과'] == '미확정']['금액_숫자'].sum())
    agreement_rate = (confirmed_count / total_count * 100) if total_count > 0 else 0
    
    return {
        'total_count': total_count,
        'total_amount': total_amount,
        'confirmed_count': confirmed_count,
        'unconfirmed_count': unconfirmed_count,
        'confirmed_amount': confirmed_amount,
        'unconfirmed_amount': unconfirmed_amount,
        'agreement_rate': agreement_rate
    }

def display_stats_metrics(stats):
    """통계 메트릭 표시"""
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📌 전체 상담건수", f"{stats['total_count']}건")
    with col2:
        st.metric("💰 총 상담액", f"{stats['total_amount']:,}원")
    with col3:
        st.metric("🎯 동의율", f"{stats['agreement_rate']:.1f}%")
    
    col4, col5 = st.columns(2)
    with col4:
        st.metric("✅ 확정 건수", f"{stats['confirmed_count']}건")
        st.metric("✅ 확정 상담액", f"{stats['confirmed_amount']:,}원")
    with col5:
        st.metric("❌ 미확정 건수", f"{stats['unconfirmed_count']}건")
        st.metric("❌ 미확정 상담액", f"{stats['unconfirmed_amount']:,}원")

def get_counselor_stats(df, counselors):
    """상담자별 통계 계산"""
    counselor_stats_list = []
    for counselor in counselors:
        counselor_data = df[df['상담자'] == counselor]
        
        total_count = len(counselor_data)
        confirmed = len(counselor_data[counselor_data['상담결과'] == '확정'])
        unconfirmed = len(counselor_data[counselor_data['상담결과'] == '미확정'])
        
        # 확정/미확정 매출 분리
        confirmed_amount = int(counselor_data[counselor_data['상담결과'] == '확정']['금액_숫자'].sum())
        unconfirmed_amount = int(counselor_data[counselor_data['상담결과'] == '미확정']['금액_숫자'].sum())
        
        agreement_rate = (confirmed / total_count * 100) if total_count > 0 else 0
        
        counselor_stats_list.append({
            '상담자': counselor,
            '상담건수': total_count,
            '확정건수': confirmed,
            '미확정건수': unconfirmed,
            '동의율': f"{agreement_rate:.1f}%",
            '확정매출_숫자': confirmed_amount,  # 정렬용 숫자
            '확정매출': f"{confirmed_amount:,}원",
            '미확정매출': f"{unconfirmed_amount:,}원"
        })
    
    result_df = pd.DataFrame(counselor_stats_list)
    
    # 확정매출 기준 내림차순 정렬
    result_df = result_df.sort_values('확정매출_숫자', ascending=False)
    
    # 정렬용 컬럼 제거
    result_df = result_df.drop('확정매출_숫자', axis=1)
    
    return result_df.reset_index(drop=True)

# ===== 🔒 로그인 기능 =====
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>🔐 더뉴치과 상담일지</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>비밀번호를 입력하세요</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            password = st.text_input("🔑 비밀번호", type="password", placeholder="비밀번호 입력")
            submitted = st.form_submit_button("🔓 로그인", use_container_width=True)
            
            if submitted:
                if password == "2874":
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("❌ 비밀번호가 틀렸습니다. 다시 입력해주세요.")
    st.stop()

# ===== 로그인 성공 후 앱 시작 =====
st.title("📂 더뉴치과 상담일지")

EXPECTED_COLS = ["날짜", "상담자", "진단원장", "환자성함", "차트번호", "분류", "상담결과", "금액", "주요포인트", "상담내용", "리콜상태"]
COUNSELORS = ["우다혜", "전누리", "임예린"]
DOCTORS = ["김동현 원장", "김언형 원장", "정성영 원장", "박경리 원장", "권영은 원장"]

# 데이터 로드 (Session State 사용)
if "df_cache" not in st.session_state:
    st.session_state.df_cache = load_gsheet_data()

df = st.session_state.df_cache

# ===== 6개 탭 생성 (정렬된 순서) =====
tabs_list = st.tabs([
    "📝 상담일지 작성", 
    "📞 미확정 리마인더", 
    "🔍 상담일지 조회", 
    "📊 보고 자료",
    "📥 자료 다운로드"
])

# 탭 변수 매핑
tab_write = tabs_list[0]      # 상담일지 작성
tab_reminder = tabs_list[1]   # 미확정 리마인더
tab_report = tabs_list[2]     # 기간 별 상담일지
tab_integrated = tabs_list[3] # 보고 자료
tab_download = tabs_list[4]   # 자료 다운로드

# ===== TAB 1: 상담일지 작성 =====
with tab_write:
    st.header("📝 상담일지 작성")
    
    # 입력 날짜 선택 (우측 상단)
    col_date = st.columns([3, 1])[1]
    with col_date:
        today = datetime.now().date()
        input_date = st.date_input("📅 입력 날짜", today, key="tab1_date")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        consultant = st.selectbox("👤 담당 상담자", [None] + COUNSELORS, format_func=lambda x: "선택하세요" if x is None else x, key="tab1_counselor")
    with col2:
        doctor = st.selectbox("👨‍⚕️ 진단 원장님", [None] + DOCTORS, format_func=lambda x: "선택하세요" if x is None else x, key="tab1_doctor")
    with col3:
        result = st.selectbox("📢 결과", [None, "미확정", "확정"], format_func=lambda x: "선택하세요" if x is None else x, key="tab1_result")
    
    col3, col4, col5 = st.columns(3)
    with col3:
        category = st.selectbox("🏥 분류", ["예약 신환", "미예약 신환", "예약 구환", "미예약 구환"], key="tab1_category")
    with col4:
        name = st.text_input("👤 환자 성함", key="tab1_name")
    with col5:
        chart_no = st.text_input("🔢 차트 번호", key="tab1_chart")

    amount = st.number_input("💰 금액 (원)", min_value=0, step=10000, format="%d", key="tab1_amount")
    points = st.text_input("📍 주요 포인트", key="tab1_points")
    content = st.text_area("💬 상세 상담 내용", height=150, key="tab1_content")

    if st.button("💾 저장하기", use_container_width=True):
        # 필수 필드 검증
        if not name:
            st.error("❌ 환자 성함을 입력해주세요!")
        elif not content:
            st.error("❌ 상담 내용을 입력해주세요!")
        elif consultant is None:
            st.error("❌ 상담자를 선택해주세요!")
        elif doctor is None:
            st.error("❌ 진단 원장을 선택해주세요!")
        elif result is None:
            st.error("❌ 상담 결과를 선택해주세요!")
        else:
            # Google Sheets 연결 확인
            if df.empty:
                st.error("❌ Google Sheets에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.")
            else:
                new_entry = pd.DataFrame([{
                    "날짜": input_date.strftime("%Y-%m-%d"),
                    "상담자": consultant,
                    "진단원장": doctor,
                    "환자성함": name,
                    "차트번호": chart_no,
                    "분류": category,
                    "상담결과": result,
                    "금액": amount,
                    "주요포인트": points,
                    "상담내용": content,
                    "리콜상태": "미리콜"
                }])
                try:
                    updated_df = pd.concat([df, new_entry], ignore_index=True)
                    if save_to_gsheet(updated_df[EXPECTED_COLS]):
                        st.session_state.df_cache = updated_df
                        st.success("✅ 저장되었습니다!", icon="✅")
                        st.balloons()  # 풍선 효과
                        
                        # 저장된 데이터 표시
                        st.subheader("📝 방금 저장된 내용")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**환자명:** {name}")
                        st.write(f"**상담자:** {consultant}")
                        st.write(f"**진단원장:** {doctor}")
                        st.write(f"**분류:** {category}")
                    with col2:
                        st.write(f"**날짜:** {input_date}")
                        st.write(f"**결과:** {result}")
                        st.write(f"**금액:** {amount:,}원")
                        st.write(f"**차트번호:** {chart_no}")
                    
                    st.write(f"**주요포인트:** {points}")
                    st.write(f"**상담내용:** {content}")
                    
                    st.divider()
                    
                    # 오늘의 입력 내역
                    st.subheader("📋 오늘의 입력 내역")
                    today = datetime.now().date().strftime("%Y-%m-%d")
                    today_data = updated_df[updated_df['날짜'] == today].copy()
                    
                    if not today_data.empty:
                        today_data = today_data.iloc[::-1]
                        st.write(f"총 **{len(today_data)}건** 입력됨")
                        
                        for idx, row in today_data.iterrows():
                            with st.expander(f"📌 {row['환자성함']} - {row['상담자']} ({row['상담결과']})"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**진단원장:** {row['진단원장']}")
                                    st.write(f"**분류:** {row['분류']}")
                                    st.write(f"**금액:** {int(float(row['금액'])):,}원")
                                with col2:
                                    st.write(f"**차트번호:** {row['차트번호']}")
                                    st.write(f"**주요포인트:** {row['주요포인트']}")
                                st.write(f"**상담내용:** {row['상담내용']}")
                    
                    st.divider()
                    st.info("✏️ 페이지를 새로고침하면 입력칸이 초기화됩니다")
                except Exception as e:
                    st.error("❌ 저장 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

# ===== TAB 2: 상담 보고 (보고용) =====
with tab_report:
    st.header("🔍 상담일지 조회")
    
    # 데이터 새로 읽기 (최신 데이터 가져오기)
    try:
        df_tab2_source = load_gsheet_data()
        df_tab2_source = df_tab2_source.dropna(subset=["환자성함"]).copy()
    except Exception as e:
        st.warning("⚠️ Google Sheets 연결 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        df_tab2_source = pd.DataFrame()
    
    # 모드 선택
    st.write("**조회 방식을 선택하세요:**")
    mode = st.radio("", ["📅 기간 선택", "🔍 환자 검색"], horizontal=True, key="tab_report_mode")
    
    st.divider()
    
    if not df_tab2_source.empty:
        if mode == "📅 기간 선택":
            # 기간 선택 모드
            col1, col2, col3 = st.columns(3)
            with col1:
                selected_counselor_tab2 = st.selectbox("👤 상담자 선택", ["전체"] + COUNSELORS, key="tab2_counselor")
            with col2:
                today = datetime.now().date()
                start_date_tab2 = st.date_input("시작일", today, key="tab2_start")
            with col3:
                end_date_tab2 = st.date_input("종료일", today, key="tab2_end")
            
            df_tab2 = df_tab2_source.copy()
            
            start_str = start_date_tab2.strftime("%Y-%m-%d")
            end_str = end_date_tab2.strftime("%Y-%m-%d")
            df_tab2 = df_tab2[(df_tab2['날짜'] >= start_str) & (df_tab2['날짜'] <= end_str)]
            
            if selected_counselor_tab2 != "전체":
                df_tab2 = df_tab2[df_tab2['상담자'] == selected_counselor_tab2]
            
            if not df_tab2.empty:
                # 상담 건수 표시
                st.metric("📌 상담 건수", f"{len(df_tab2)}건")
                st.divider()
                
                df_tab2 = df_tab2.iloc[::-1]
                
                st.subheader("📝 상담내용 상세")
                for idx, row in df_tab2.iterrows():
                    with st.expander(f"📌 {row['날짜']} - {row['환자성함']} (차트: {format_chart_no(row['차트번호'])}) - {row['상담자']}", expanded=True):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"**분류:** {row['분류']}")
                            st.write(f"**금액:** {format_amount(row['금액']):,}원")
                        with col2:
                            st.write(f"**진단원장:** {row['진단원장']}")
                            # 상담결과 색상 구분
                            if row['상담결과'] == '확정':
                                st.markdown(f"**상담결과:** <span style='color: blue; font-weight: bold;'>확정</span>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"**상담결과:** <span style='color: red; font-weight: bold;'>미확정</span>", unsafe_allow_html=True)
                        with col3:
                            st.write(f"**차트번호:** {format_chart_no(row['차트번호'])}")
                        
                        st.markdown(f"**주요포인트:** {row['주요포인트']}")
                        st.markdown(f"**상담내용:**\n\n{row['상담내용']}")
            else:
                st.info("조회할 데이터가 없습니다")
        
        else:  # 환자 검색 모드
            st.write("환자 이름 또는 차트번호로 검색하세요. (부분 검색 가능)")
            search_patient = st.text_input("🔍 환자 이름 또는 차트번호 검색", placeholder="예: 송호선, 12345 등", key="tab_report_search")
            
            if search_patient:
                # 환자 이름 또는 차트번호로 검색
                df_search = df_tab2_source[
                    (df_tab2_source['환자성함'].str.contains(search_patient, case=False, na=False)) | 
                    (df_tab2_source['차트번호'].astype(str).str.contains(search_patient, case=False, na=False))
                ].copy()
                
                if not df_search.empty:
                    df_search = df_search.iloc[::-1]
                    
                    st.success(f"✅ '{search_patient}' 검색 결과: {len(df_search)}건")
                    st.divider()
                    
                    for idx, row in df_search.iterrows():
                        chart_num = format_chart_no(row['차트번호'])
                        with st.expander(
                            f"📌 {row['날짜']} - {row['환자성함']} (차트: {chart_num}) - {row['상담자']}", 
                            expanded=True
                        ):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.write(f"**분류:** {row['분류']}")
                                st.write(f"**금액:** {format_amount(row['금액']):,}원")
                            with col2:
                                st.write(f"**진단원장:** {row['진단원장']}")
                                # 상담결과 색상 구분
                                if row['상담결과'] == '확정':
                                    st.markdown(f"**상담결과:** <span style='color: blue; font-weight: bold;'>확정</span>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"**상담결과:** <span style='color: red; font-weight: bold;'>미확정</span>", unsafe_allow_html=True)
                            with col3:
                                st.write(f"**차트번호:** {chart_num}")
                            
                            st.markdown(f"**주요포인트:** {row['주요포인트']}")
                            st.markdown(f"**상담내용:**\n\n{row['상담내용']}")
                else:
                    st.warning(f"❌ '{search_patient}'에 해당하는 환자가 없습니다.")
            else:
                st.info("환자 이름 또는 차트번호를 입력해주세요.")
    else:
        st.info("데이터가 없습니다")

# ===== TAB 3: 상담 내용 조회 (환자 검색) =====

# ===== TAB 3: 미확정 상담 리마인더 =====
with tab_reminder:
    st.header("📞 미확정 상담 리마인더")
    
    col1, col2 = st.columns(2)
    with col1:
        reminder_counselor = st.selectbox("👤 상담자 선택", ["전체"] + COUNSELORS, key="tab5_counselor")
    with col2:
        st.write("")
    
    if not df.empty:
        df_reminder = df[df['상담결과'] == '미확정'].copy()
        
        if reminder_counselor != "전체":
            df_reminder = df_reminder[df_reminder['상담자'] == reminder_counselor]
        
        if not df_reminder.empty:
            today = datetime.now().date()
            df_reminder['경과일'] = df_reminder['날짜'].apply(
                lambda x: (today - datetime.strptime(x, "%Y-%m-%d").date()).days
            )
            df_reminder = df_reminder[df_reminder['경과일'] >= 7]
            
            if not df_reminder.empty:
                df_reminder['리콜상태'] = df_reminder['리콜상태'].fillna('미리콜')
                
                df_need_recall = df_reminder[df_reminder['리콜상태'] == '미리콜'].sort_values('경과일', ascending=False)
                df_recalled = df_reminder[df_reminder['리콜상태'] == '리콜완료'].sort_values('경과일', ascending=False)
                
                # 미리콜 (상단)
                if not df_need_recall.empty:
                    st.subheader(f"🔴 리콜 필요 ({len(df_need_recall)}명)")
                    st.divider()
                    for idx, row in df_need_recall.iterrows():
                        with st.expander(
                            f"👤 {row['환자성함']} | 차트: {format_chart_no(row['차트번호'])} | {row['경과일']}일 경과 | {format_amount(row['금액']):,}원 | ❌ {row['상담결과']} | {row['상담자']}", 
                            expanded=True
                        ):
                            col1, col2 = st.columns([3, 1])
                            
                            with col1:
                                st.markdown(f"**주요포인트:** {row['주요포인트']}")
                                st.markdown(f"**상담내용:**\n\n{row['상담내용']}")
                            
                            with col2:
                                if st.button("✅ 리콜완료", key=f"recall_{idx}", use_container_width=True):
                                    st.session_state[f"confirm_{idx}"] = True
                            
                            if st.session_state.get(f"confirm_{idx}", False):
                                st.warning("정말 리콜완료 하시겠습니까?")
                                col_yes, col_no = st.columns(2)
                                with col_yes:
                                    if st.button("✔️ 확인", key=f"confirm_yes_{idx}", use_container_width=True):
                                        df.loc[df.index == idx, '리콜상태'] = '리콜완료'
                                        if save_to_gsheet(df[EXPECTED_COLS]):
                                            st.session_state.df_cache = df
                                            st.session_state[f"confirm_{idx}"] = False
                                            st.success("리콜 완료되었습니다!")
                                            st.rerun()
                                with col_no:
                                    if st.button("❌ 취소", key=f"confirm_no_{idx}", use_container_width=True):
                                        st.session_state[f"confirm_{idx}"] = False
                                        st.rerun()
                
                # 리콜완료 (하단)
                if not df_recalled.empty:
                    st.divider()
                    with st.expander(f"✅ 리콜 완료 ({len(df_recalled)}명)", expanded=False):
                        for idx, row in df_recalled.iterrows():
                            with st.expander(
                                f"👤 {row['환자성함']} | 차트: {format_chart_no(row['차트번호'])} | {row['경과일']}일 | {format_amount(row['금액']):,}원 | {row['상담자']}", 
                                expanded=False
                            ):
                                col1, col2 = st.columns([3, 1])
                                
                                with col1:
                                    st.markdown(f"**주요포인트:** {row['주요포인트']}")
                                    st.markdown(f"**상담내용:**\n\n{row['상담내용']}")
                                
                                with col2:
                                    if st.button("↩️ 리콜 재진행", key=f"undo_recall_{idx}", use_container_width=True):
                                        st.session_state[f"confirm_undo_{idx}"] = True
                                
                                if st.session_state.get(f"confirm_undo_{idx}", False):
                                    st.warning("리콜 완료를 취소하고 미리콜로 변경하시겠습니까?")
                                    col_yes, col_no = st.columns(2)
                                    with col_yes:
                                        if st.button("✔️ 확인", key=f"confirm_undo_yes_{idx}", use_container_width=True):
                                            df.loc[df.index == idx, '리콜상태'] = '미리콜'
                                            if save_to_gsheet(df[EXPECTED_COLS]):
                                                st.session_state.df_cache = df
                                                st.session_state[f"confirm_undo_{idx}"] = False
                                                st.success("미리콜로 변경되었습니다!")
                                                st.rerun()
                                    with col_no:
                                        if st.button("❌ 취소", key=f"confirm_undo_no_{idx}", use_container_width=True):
                                            st.session_state[f"confirm_undo_{idx}"] = False
                                            st.rerun()
            else:
                st.info("🎉 리콜 필요한 상담이 없습니다!")
        else:
            st.info("미확정 상담이 없습니다.")
    else:
        st.info("데이터가 없습니다.")

# ===== TAB 5: 상담 일지 통계 =====
# ===== TAB 5: 상담 보고 =====
with tab_integrated:
    st.header("📄 상담 보고")
    
    # 데이터 새로고침
    try:
        df_integrated = load_gsheet_data()
        df_integrated = df_integrated.dropna(subset=["환자성함"]).copy()
        if '진단원장' not in df_integrated.columns:
            df_integrated['진단원장'] = ''
        if '리콜상태' not in df_integrated.columns:
            df_integrated['리콜상태'] = '미리콜'
    except Exception as e:
        st.warning("⚠️ Google Sheets 연결 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        df_integrated = pd.DataFrame()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_counselor_integrated = st.selectbox("👤 상담자 선택", ["전체"] + COUNSELORS, key="integrated_counselor")
    with col2:
        today = datetime.now().date()
        start_date_integrated = st.date_input("시작일", today, key="integrated_start")
    with col3:
        end_date_integrated = st.date_input("종료일", today, key="integrated_end")
    
    if not df_integrated.empty:
        df_report = df_integrated.copy()
        df_report['금액_숫자'] = pd.to_numeric(df_report['금액'], errors='coerce').fillna(0)
        
        start_str = start_date_integrated.strftime("%Y-%m-%d")
        end_str = end_date_integrated.strftime("%Y-%m-%d")
        df_report = df_report[(df_report['날짜'] >= start_str) & (df_report['날짜'] <= end_str)]
        
        if selected_counselor_integrated != "전체":
            df_report = df_report[df_report['상담자'] == selected_counselor_integrated]
        
        if not df_report.empty:
            # 1. 상담일지 통계 (상단)
            stats_integrated = calculate_stats(df_report)
            st.subheader("📊 상담일지 통계")
            display_stats_metrics(stats_integrated)
            
            st.divider()
            
            # 2. 상담자별 매출 및 성과
            if selected_counselor_integrated == "전체":
                st.subheader("👥 상담자별 매출 및 성과")
                
                counselor_sales_df = get_counselor_stats(df_report, COUNSELORS)
                st.dataframe(counselor_sales_df, use_container_width=True, hide_index=True)
                
                st.divider()
            
            # 3. 분류별 상담 현황
            st.subheader("📋 분류별 상담 현황 (확정/미확정)")
            
            category_order = ['예약 신환', '미예약 신환', '예약 구환', '미예약 구환']
            
            category_result_data = []
            for category in category_order:
                category_df = df_report[df_report['분류'] == category]
                confirmed = len(category_df[category_df['상담결과'] == '확정'])
                unconfirmed = len(category_df[category_df['상담결과'] == '미확정'])
                
                category_result_data.append({
                    '분류': category,
                    '확정': confirmed,
                    '미확정': unconfirmed,
                    '합계': confirmed + unconfirmed
                })
            
            category_result_df = pd.DataFrame(category_result_data)
            st.dataframe(category_result_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # 4. 상담내용 상세
            st.metric("📌 상담 건수", f"{len(df_report)}건")
            st.divider()
            
            df_report = df_report.iloc[::-1]
            
            st.subheader("📝 상담내용 상세")
            for idx, row in df_report.iterrows():
                with st.expander(f"📌 {row['날짜']} - {row['환자성함']} (차트: {format_chart_no(row['차트번호'])}) - {row['상담자']}", expanded=True):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**분류:** {row['분류']}")
                        st.write(f"**금액:** {format_amount(row['금액']):,}원")
                    with col2:
                        st.write(f"**진단원장:** {row['진단원장']}")
                        # 상담결과 색상 구분
                        if row['상담결과'] == '확정':
                            st.markdown(f"**상담결과:** <span style='color: blue; font-weight: bold;'>확정</span>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"**상담결과:** <span style='color: red; font-weight: bold;'>미확정</span>", unsafe_allow_html=True)
                    with col3:
                        st.write(f"**차트번호:** {format_chart_no(row['차트번호'])}")
                    
                    st.markdown(f"**주요포인트:** {row['주요포인트']}")
                    st.markdown(f"**상담내용:**\n\n{row['상담내용']}")
        else:
            st.info("해당 기간에 상담 기록이 없습니다")
    else:
        st.info("데이터가 없습니다")

# ===== TAB 6: 자료 다운로드 =====
with tab_download:
    st.header("📥 자료 다운로드")
    
    # 비밀번호 입력
    report_password = st.text_input("🔐 비밀번호 입력", type="password", placeholder="비밀번호를 입력하세요", key="tab7_password")
    
    if report_password == "2872":
        col1, col2, col3 = st.columns(3)
        with col1:
            report_counselor = st.selectbox("👤 상담자 선택", ["전체"] + COUNSELORS, key="tab7_counselor")
        with col2:
            today = datetime.now().date()
            report_start_date = st.date_input("시작일", today, key="tab7_start")
        with col3:
            report_end_date = st.date_input("종료일", today, key="tab7_end")
    
    if report_password == "2872":
        
        if not df.empty:
            df_report = df.copy()
            df_report['금액_숫자'] = pd.to_numeric(df_report['금액'], errors='coerce').fillna(0)
            
            start_str = report_start_date.strftime("%Y-%m-%d")
            end_str = report_end_date.strftime("%Y-%m-%d")
            df_report = df_report[(df_report['날짜'] >= start_str) & (df_report['날짜'] <= end_str)]
            
            if report_counselor != "전체":
                df_report = df_report[df_report['상담자'] == report_counselor]
            
            if not df_report.empty:
                # 통계 계산
                stats = calculate_stats(df_report)
                total_count = stats['total_count']
                total_amount = stats['total_amount']
                confirmed_count = stats['confirmed_count']
                unconfirmed_count = stats['unconfirmed_count']
                confirmed_amount = stats['confirmed_amount']
                unconfirmed_amount = stats['unconfirmed_amount']
                agreement_rate = stats['agreement_rate']
                
                # 상단 통계 표시
                st.subheader("📊 상담 통계")
                display_stats_metrics(stats)
                
                st.divider()
                
                # 상담자별 매출 및 성과
                st.subheader("👥 상담자별 매출 및 성과")
                
                if report_counselor == "전체":
                    counselor_sales_df = get_counselor_stats(df_report, COUNSELORS)
                    st.dataframe(counselor_sales_df, use_container_width=True, hide_index=True)
                else:
                    st.info("전체 상담자를 선택해야 상담자별 성과를 볼 수 있습니다.")
                
                st.divider()
                
                # 상담 보고 내용
                st.subheader("📝 상담 보고 내용")
                df_report_sorted = df_report.iloc[::-1]
                
                for idx, row in df_report_sorted.iterrows():
                    with st.expander(
                        f"📌 {row['날짜']} - {row['환자성함']} (차트: {format_chart_no(row['차트번호'])}) - {row['상담자']}", 
                        expanded=False
                    ):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**진단 원장:** {row['진단원장']}")
                            st.write(f"**분류:** {row['분류']}")
                            # 상담결과 색상 구분
                            if row['상담결과'] == '확정':
                                st.markdown(f"**상담결과:** <span style='color: blue; font-weight: bold;'>확정</span>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"**상담결과:** <span style='color: red; font-weight: bold;'>미확정</span>", unsafe_allow_html=True)
                        with col2:
                            st.write(f"**금액:** {format_amount(row['금액']):,}원")
                            st.write(f"**상담자:** {row['상담자']}")
                        
                        st.markdown(f"**주요포인트:** {row['주요포인트']}")
                        st.markdown(f"**상담내용:**\n\n{row['상담내용']}")
                
                st.divider()
                
                # Excel 다운로드
                st.subheader("📥 Excel 다운로드")
                
                try:
                    import openpyxl
                    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
                    from io import BytesIO
                    
                    # Excel 파일 생성
                    output = BytesIO()
                    
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        # 1. 통계 시트
                        stats_data = {
                            '항목': ['전체 상담건수', '총 상담액', '동의율', '확정 건수', '확정 상담액', '미확정 건수', '미확정 상담액'],
                            '값': [f"{total_count}건", f"{total_amount:,}원", f"{agreement_rate:.1f}%", 
                                   f"{confirmed_count}건", f"{confirmed_amount:,}원", f"{unconfirmed_count}건", f"{unconfirmed_amount:,}원"]
                        }
                        stats_df = pd.DataFrame(stats_data)
                        stats_df.to_excel(writer, sheet_name='통계', index=False)
                        
                        # 2. 상담자별 성과 시트
                        if report_counselor == "전체":
                            counselor_sales_df.to_excel(writer, sheet_name='상담자별성과', index=False)
                        
                        # 3. 상담 내용 시트
                        report_export_df = df_report_sorted[['날짜', '상담자', '진단원장', '환자성함', '차트번호', '분류', '상담결과', '금액', '주요포인트', '상담내용']].copy()
                        report_export_df.to_excel(writer, sheet_name='상담내용', index=False)
                    
                    output.seek(0)
                    
                    st.download_button(
                        label="📥 Excel 파일 다운로드",
                        data=output.getvalue(),
                        file_name=f"더뉴치과_상담보고_{report_start_date.strftime('%Y%m%d')}_{report_end_date.strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                except ImportError:
                    st.warning("⚠️ Excel 기능을 사용하려면 openpyxl 라이브러리가 필요합니다.")
                
                st.divider()
                
                # PNG 이미지 다운로드 (ZIP 파일로 통합)
                st.subheader("📸 이미지 다운로드 (카톡 공유용)")
                
                # ZIP 파일 생성
                plt.rcParams['font.family'] = 'DejaVu Sans'
                plt.rcParams['axes.unicode_minus'] = False
                
                # 한글 폰트 시도 (시스템에 따라 다름)
                try:
                    import matplotlib.font_manager as fm
                    # 시스템 한글 폰트 찾기
                    font_names = [f.name for f in fm.fontManager.ttflist]
                    if 'Noto Sans CJK JP' in font_names:
                        plt.rcParams['font.family'] = 'Noto Sans CJK JP'
                    elif 'DejaVu Sans' in font_names:
                        plt.rcParams['font.family'] = 'DejaVu Sans'
                except:
                    pass
                
                # ZIP 파일 생성
                zip_buffer = BytesIO()
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # 1. 통계 정보 이미지
                    fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
                    ax.axis('off')
                    
                    stats_text = f"""Consultation Statistics
{report_start_date} ~ {report_end_date}
Counselor: {report_counselor if report_counselor != '전체' else 'All'}

{'='*60}

Total Consultations: {total_count}
Total Amount: ₩ {total_amount:,}
Agreement Rate: {agreement_rate:.1f}%

Confirmed: {confirmed_count}
Confirmed Amount: ₩ {confirmed_amount:,}

Unconfirmed: {unconfirmed_count}
Unconfirmed Amount: ₩ {unconfirmed_amount:,}

{'='*60}"""
                    
                    ax.text(0.5, 0.5, stats_text, ha='center', va='center', 
                           fontsize=11, family='monospace',
                           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3))
                    
                    img_bytes = BytesIO()
                    plt.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
                    img_bytes.seek(0)
                    plt.close()
                    
                    zf.writestr('1_Statistics.png', img_bytes.getvalue())
                    
                    # 2. 상담자별 성과 이미지
                    if report_counselor == "전체":
                        fig, ax = plt.subplots(figsize=(14, 8), dpi=100)
                        ax.axis('off')
                        
                        perf_text = "Counselor Performance\n\n"
                        perf_text += "Name | Count | OK | X | Rate | Confirmed Sales | Unconfirmed Sales\n"
                        perf_text += "="*100 + "\n"
                        
                        for _, row in counselor_sales_df.iterrows():
                            perf_text += f"{row['상담자']} | {row['상담건수']} | {row['확정건수']} | {row['미확정건수']} | {row['동의율']} | {row['확정매출']} | {row['미확정매출']}\n"
                        
                        ax.text(0.05, 0.95, perf_text, ha='left', va='top', 
                               fontsize=9, family='monospace',
                               bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.2))
                        
                        img_bytes = BytesIO()
                        plt.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
                        img_bytes.seek(0)
                        plt.close()
                        
                        zf.writestr('2_Performance.png', img_bytes.getvalue())
                    
                    # 3. 상담 내용 이미지
                    num_cases = len(df_report_sorted)
                    fig_height = max(10, 5 + (num_cases * 0.6))
                    
                    fig, ax = plt.subplots(figsize=(14, fig_height), dpi=100)
                    ax.axis('off')
                    
                    content_text = f"""Consultation Details
{report_start_date} ~ {report_end_date}
Counselor: {report_counselor if report_counselor != '전체' else 'All'}
Total: {num_cases} cases

"""
                    
                    for _, row in df_report_sorted.iterrows():
                        content_text += f"\n[{row['날짜']}] {row['환자성함']}\n"
                        content_text += f"Counselor: {row['상담자']} | Doctor: {row['진단원장']}\n"
                        content_text += f"Type: {row['분류']} | Result: {row['상담결과']} | Amount: {format_amount(row['금액']):,}\n"
                        content_text += f"Point: {row['주요포인트']}\n"
                        content_text += "-"*70 + "\n"
                    
                    ax.text(0.05, 0.98, content_text, ha='left', va='top', 
                           fontsize=8, family='monospace',
                           bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.2))
                    
                    img_bytes = BytesIO()
                    plt.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
                    img_bytes.seek(0)
                    plt.close()
                    
                    zf.writestr('3_ConsultationDetails.png', img_bytes.getvalue())
                
                zip_buffer.seek(0)
                
                st.download_button(
                    label="📥 모든 이미지 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name=f"더뉴치과_이미지_{report_start_date.strftime('%Y%m%d')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                
                st.divider()
            else:
                st.info("해당 기간에 상담 기록이 없습니다")
        else:
            st.info("데이터가 없습니다")
    
    elif report_password:
        st.error("❌ 비밀번호가 틀렸습니다.")
