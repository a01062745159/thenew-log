import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import matplotlib.pyplot as plt

# 페이지 설정
st.set_page_config(page_title="더뉴치과 상담일지", layout="wide")

# ===== 로그인 =====
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🔐 더뉴치과 상담일지</h2>", unsafe_allow_html=True)
    
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
def get_worksheet():
    """Google Sheets 워크시트 연결"""
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
        st.error(f"🚨 Google Sheets 연결 실패: {str(e)}")
        return None

def load_all_data():
    """Google Sheets의 모든 데이터 로드"""
    try:
        worksheet = get_worksheet()
        if worksheet:
            data = worksheet.get_all_records()
            if data:
                return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {str(e)}")
        return pd.DataFrame()

# ===== 메인 앱 =====
st.title("📂 더뉴치과 상담일지")

# 탭 생성
tab1, tab2, tab3 = st.tabs(["📝 상담일지 작성", "🔍 상담일지 조회", "📊 상담 보고"])

# ===== TAB 1: 상담일지 작성 =====
with tab1:
    st.header("📋 상담 정보 입력")
    
    # 입력 날짜 (전체 너비)
    st.markdown("**📅 입력 날짜**")
    date = st.date_input("", datetime.now().date(), label_visibility="collapsed", key="tab1_date")
    
    st.divider()
    
    # 첫 번째 행: 담당 상담자 / 진단 원장님 / 결과
    col1, col2, col3 = st.columns(3)
    with col1:
        consultant = st.selectbox("👤 담당 상담자", ["우다혜", "전누리", "임예린"])
    with col2:
        doctor = st.selectbox("🩺 진단 원장님", ["김동현 원장", "김언형 원장", "정성영 원장", "박경리 원장", "권영은 원장"])
    with col3:
        result = st.selectbox("✅ 결과", ["확정", "미확정"])
    
    # 두 번째 행: 분류 / 환자 성함 / 차트번호
    col1, col2, col3 = st.columns(3)
    with col1:
        category = st.selectbox("📂 분류", ["예약 신환", "미예약 신환", "예약 구환", "미예약 구환"])
    with col2:
        patient_name = st.text_input("👤 환자 성함", placeholder="이름 입력")
    with col3:
        chart_no = st.text_input("🔢 차트번호", placeholder="번호 입력")
    
    # 세 번째 행: 금액 (full width)
    amount = st.text_input("💰 금액", placeholder="0", value="0")
    
    # 네 번째 행: 주요포인트
    main_point = st.text_input("⭐ 주요포인트", placeholder="포인트 입력")
    
    # 다섯 번째 행: 상세 상담 내용
    content = st.text_area("💬 상세 상담 내용", placeholder="상담 내용을 입력하세요...", height=200)
    
    # 숨겨진 필드 (저장용)
    recall_status = "미리콜"
    
    # ===== 저장 버튼 =====
    if st.button("💾 저장하기", use_container_width=True):
        if not patient_name:
            st.error("❌ 환자성함을 입력해주세요!")
        elif not content:
            st.error("❌ 상담내용을 입력해주세요!")
        else:
            worksheet = get_worksheet()
            if worksheet:
                try:
                    # 데이터 준비
                    new_row = [
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
                    
                    # Google Sheets에 행 추가
                    worksheet.append_row(new_row)
                    
                    st.success("✅ 저장되었습니다!")
                    st.balloons()
                    
                    # 저장된 내용 표시
                    st.subheader("📝 방금 저장된 내용")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**담당 상담자:** {consultant}")
                    with col2:
                        st.write(f"**진단 원장님:** {doctor}")
                    with col3:
                        st.write(f"**결과:** {result}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**분류:** {category}")
                    with col2:
                        st.write(f"**환자 성함:** {patient_name}")
                    with col3:
                        st.write(f"**차트번호:** {chart_no}")
                    
                    st.write(f"**금액:** {amount}")
                    st.write(f"**주요포인트:** {main_point}")
                    st.write(f"**상세 상담 내용:** {content}")
                    
                except Exception as e:
                    st.error(f"🚨 저장 중 에러 발생: {str(e)}")

# ===== TAB 2: 상담일지 조회 =====
with tab2:
    st.header("🔍 상담일지 조회")
    
    # 조회 방식 선택
    search_type = st.radio("조회 방식을 선택하세요:", ["기간선택", "환자검색"], horizontal=True)
    
    if search_type == "기간선택":
        st.subheader("📅 기간 선택")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("시작일", datetime.now().date(), key="tab2_start")
        with col2:
            end_date = st.date_input("종료일", datetime.now().date(), key="tab2_end")
        
        # 데이터 로드 및 필터링
        df = load_all_data()
        
        if not df.empty:
            # 날짜 필터링
            df['날짜'] = pd.to_datetime(df['날짜'])
            start_date_str = pd.to_datetime(start_date)
            end_date_str = pd.to_datetime(end_date)
            
            filtered_df = df[(df['날짜'] >= start_date_str) & (df['날짜'] <= end_date_str)]
            
            if not filtered_df.empty:
                st.success(f"✅ {len(filtered_df)}건의 상담 기록을 찾았습니다.")
                st.divider()
                
                # 역순으로 정렬 (최신순)
                filtered_df = filtered_df.iloc[::-1]
                
                # 상담 내용 상세 표시
                for idx, row in filtered_df.iterrows():
                    with st.expander(f"📌 {row['날짜'].strftime('%Y-%m-%d')} - {row['환자성함']} (차트: {row['차트번호']}) - {row['상담자']}", expanded=True):
                        # 첫 번째 행: 분류 / 진단원장 / 차트번호
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"**분류:** {row['분류']}")
                        with col2:
                            st.write(f"**진단원장:** {row['진단원장']}")
                        with col3:
                            st.write(f"**차트번호:** {row['차트번호']}")
                        
                        # 두 번째 행: 금액 / 상담결과 (색상)
                        col1, col2 = st.columns(2)
                        with col1:
                            try:
                                amount = int(float(row['금액']))
                                st.write(f"**금액:** {amount:,}원")
                            except:
                                st.write(f"**금액:** {row['금액']}")
                        with col2:
                            if row['상담결과'] == '확정':
                                st.markdown(f"**상담결과:** <span style='color: blue; font-weight: bold;'>확정</span>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"**상담결과:** <span style='color: red; font-weight: bold;'>미확정</span>", unsafe_allow_html=True)
                        
                        # 세 번째 행: 주요포인트
                        st.write(f"**주요포인트:** {row['주요포인트']}")
                        
                        # 네 번째 행: 상담내용
                        st.write("---")
                        st.write(f"**상담내용:**\n\n{row['상담내용']}")
            else:
                st.info(f"⚠️ {start_date}부터 {end_date}까지의 상담 기록이 없습니다.")
        else:
            st.info("📭 저장된 상담 기록이 없습니다.")
    
    else:  # 환자검색
        st.subheader("👤 환자 검색")
        search_name = st.text_input("환자 성함을 입력하세요:", placeholder="이름 입력", key="tab2_search")
        
        # 데이터 로드
        df = load_all_data()
        
        if search_name and not df.empty:
            # 환자명 검색
            filtered_df = df[df['환자성함'].str.contains(search_name, na=False)]
            
            if not filtered_df.empty:
                st.success(f"✅ '{search_name}'의 상담 기록 {len(filtered_df)}건을 찾았습니다.")
                st.divider()
                
                # 역순으로 정렬 (최신순)
                filtered_df = filtered_df.iloc[::-1]
                
                # 상담 내용 상세 표시
                for idx, row in filtered_df.iterrows():
                    with st.expander(f"📌 {row['날짜']} - {row['환자성함']} (차트: {row['차트번호']}) - {row['상담자']}", expanded=True):
                        # 첫 번째 행: 분류 / 진단원장 / 차트번호
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"**분류:** {row['분류']}")
                        with col2:
                            st.write(f"**진단원장:** {row['진단원장']}")
                        with col3:
                            st.write(f"**차트번호:** {row['차트번호']}")
                        
                        # 두 번째 행: 금액 / 상담결과 (색상)
                        col1, col2 = st.columns(2)
                        with col1:
                            try:
                                amount = int(float(row['금액']))
                                st.write(f"**금액:** {amount:,}원")
                            except:
                                st.write(f"**금액:** {row['금액']}")
                        with col2:
                            if row['상담결과'] == '확정':
                                st.markdown(f"**상담결과:** <span style='color: blue; font-weight: bold;'>확정</span>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"**상담결과:** <span style='color: red; font-weight: bold;'>미확정</span>", unsafe_allow_html=True)
                        
                        # 세 번째 행: 주요포인트
                        st.write(f"**주요포인트:** {row['주요포인트']}")
                        
                        # 네 번째 행: 상담내용
                        st.write("---")
                        st.write(f"**상담내용:**\n\n{row['상담내용']}")
            else:
                st.info(f"⚠️ '{search_name}'의 상담 기록이 없습니다.")
        elif search_name:
            st.info("📭 저장된 상담 기록이 없습니다.")

# ===== TAB 3: 상담 보고 =====
with tab3:
    st.header("📊 상담 보고")
    
    # 상담자 선택 및 기간 선택
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        selected_consultant = st.selectbox("👤 상담자 선택", ["우다혜", "전누리", "임예린"], key="tab3_consultant")
    with col2:
        report_start_date = st.date_input("시작일", datetime.now().date(), key="tab3_start")
    with col3:
        report_end_date = st.date_input("종료일", datetime.now().date(), key="tab3_end")
    
    # 데이터 로드 및 필터링
    df = load_all_data()
    
    if not df.empty:
        # 날짜 필터링
        df['날짜'] = pd.to_datetime(df['날짜'])
        start_date_str = pd.to_datetime(report_start_date)
        end_date_str = pd.to_datetime(report_end_date)
        
        # 기간 및 상담자 필터링
        filtered_df = df[(df['날짜'] >= start_date_str) & 
                         (df['날짜'] <= end_date_str) &
                         (df['상담자'] == selected_consultant)]
        
        if not filtered_df.empty:
            # ===== 통계 계산 =====
            total_count = len(filtered_df)
            confirmed_count = len(filtered_df[filtered_df['상담결과'] == '확정'])
            unconfirmed_count = len(filtered_df[filtered_df['상담결과'] == '미확정'])
            
            # 금액 계산
            filtered_df['금액_숫자'] = pd.to_numeric(filtered_df['금액'], errors='coerce').fillna(0)
            total_amount = int(filtered_df['금액_숫자'].sum())
            confirmed_amount = int(filtered_df[filtered_df['상담결과'] == '확정']['금액_숫자'].sum())
            unconfirmed_amount = int(filtered_df[filtered_df['상담결과'] == '미확정']['금액_숫자'].sum())
            
            # 동의율
            agreement_rate = (confirmed_count / total_count * 100) if total_count > 0 else 0
            
            # ===== 통계 표시 =====
            st.subheader("📈 통계")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("전체 상담 건수", f"{total_count}건")
            with col2:
                st.metric("총 상담액", f"{total_amount:,}원")
            with col3:
                st.metric("동의율", f"{agreement_rate:.1f}%")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("확정 건수", f"{confirmed_count}건")
            with col2:
                st.metric("미확정 건수", f"{unconfirmed_count}건")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("확정 상담액", f"{confirmed_amount:,}원")
            with col2:
                st.metric("미확정 상담액", f"{unconfirmed_amount:,}원")
            
            st.divider()
            
            # ===== 상담자별 매출 및 성과 =====
            st.subheader("👥 상담자별 매출 및 성과")
            
            # 전체 상담자별 데이터
            all_consultants_df = df[(df['날짜'] >= start_date_str) & (df['날짜'] <= end_date_str)]
            
            if not all_consultants_df.empty:
                consultant_stats = []
                
                for consultant in ["우다혜", "전누리", "임예린"]:
                    consultant_data = all_consultants_df[all_consultants_df['상담자'] == consultant]
                    
                    if len(consultant_data) > 0:
                        cons_count = len(consultant_data)
                        cons_confirmed = len(consultant_data[consultant_data['상담결과'] == '확정'])
                        cons_unconfirmed = len(consultant_data[consultant_data['상담결과'] == '미확정'])
                        cons_rate = (cons_confirmed / cons_count * 100) if cons_count > 0 else 0
                        
                        consultant_data['금액_숫자'] = pd.to_numeric(consultant_data['금액'], errors='coerce').fillna(0)
                        cons_confirmed_amount = int(consultant_data[consultant_data['상담결과'] == '확정']['금액_숫자'].sum())
                        cons_unconfirmed_amount = int(consultant_data[consultant_data['상담결과'] == '미확정']['금액_숫자'].sum())
                        
                        consultant_stats.append({
                            "상담자": consultant,
                            "상담건수": cons_count,
                            "확정건수": cons_confirmed,
                            "미확정건수": cons_unconfirmed,
                            "동의율(%)": f"{cons_rate:.1f}",
                            "확정매출": f"{cons_confirmed_amount:,}",
                            "미확정매출": f"{cons_unconfirmed_amount:,}"
                        })
                
                consultant_df = pd.DataFrame(consultant_stats)
                st.dataframe(consultant_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # ===== 분류별 상담 현황 =====
            st.subheader("📂 분류별 상담 현황")
            
            # 분류별 통계
            category_stats = []
            for category in filtered_df['분류'].unique():
                category_data = filtered_df[filtered_df['분류'] == category]
                confirmed = len(category_data[category_data['상담결과'] == '확정'])
                unconfirmed = len(category_data[category_data['상담결과'] == '미확정'])
                
                category_stats.append({
                    "분류": category,
                    "확정": confirmed,
                    "미확정": unconfirmed
                })
            
            category_df = pd.DataFrame(category_stats)
            
            if not category_df.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.dataframe(category_df, use_container_width=True, hide_index=True)
                
                with col2:
                    # 분류별 차트
                    import matplotlib.pyplot as plt
                    fig, ax = plt.subplots(figsize=(8, 6))
                    x = range(len(category_df))
                    width = 0.35
                    
                    ax.bar([i - width/2 for i in x], category_df['확정'], width, label='확정', color='#3498db')
                    ax.bar([i + width/2 for i in x], category_df['미확정'], width, label='미확정', color='#e74c3c')
                    
                    ax.set_xlabel('분류', fontproperties='DejaVu Sans')
                    ax.set_ylabel('건수', fontproperties='DejaVu Sans')
                    ax.set_title('분류별 상담 현황', fontproperties='DejaVu Sans')
                    ax.set_xticks(x)
                    ax.set_xticklabels(category_df['분류'], fontproperties='DejaVu Sans')
                    ax.legend(fontsize=10)
                    ax.grid(axis='y', alpha=0.3)
                    
                    st.pyplot(fig)
        else:
            st.info(f"⚠️ 해당 기간에 {selected_consultant}의 상담 기록이 없습니다.")
    else:
        st.info("📭 저장된 상담 기록이 없습니다.")

# 하단 로그아웃
st.divider()
if st.button("🔓 로그아웃"):
    st.session_state.logged_in = False
    st.rerun()
