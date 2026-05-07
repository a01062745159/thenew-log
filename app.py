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

def load_all_data(force_refresh=False):
    """Google Sheets의 모든 데이터 로드 (강제 새로고침 옵션)"""
    try:
        worksheet = get_worksheet()
        if worksheet:
            # 캐시 무시하고 최신 데이터 가져오기
            data = worksheet.get_all_records(expect_headers=True)
            if data:
                return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {str(e)}")
        return pd.DataFrame()

# ===== 메인 앱 =====
st.title("📂 더뉴치과 상담일지")

# 탭 생성
tab1, tab2, tab3, tab4 = st.tabs(["📝 상담일지 작성", "📞 미확정 리마인더", "🔍 상담일지 조회", "📊 상담 보고"])

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
        consultant = st.selectbox("👤 담당 상담자", ["선택하세요.", "우다혜", "전누리", "임예린"])
    with col2:
        doctor = st.selectbox("🩺 진단 원장님", ["선택하세요.", "김동현 원장", "김언형 원장", "정성영 원장", "박경리 원장", "권영은 원장"])
    with col3:
        result = st.selectbox("✅ 결과", ["선택하세요.", "확정", "미확정"])
    
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
        # 필수 필드 검증
        if consultant == "선택하세요.":
            st.error("❌ 담당 상담자를 선택해주세요!")
        elif doctor == "선택하세요.":
            st.error("❌ 진단 원장님을 선택해주세요!")
        elif result == "선택하세요.":
            st.error("❌ 결과를 선택해주세요!")
        elif not patient_name:
            st.error("❌ 환자성함을 입력해주세요!")
        elif not content:
            st.error("❌ 상담내용을 입력해주세요!")
        else:
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
            
            # 재시도 로직 (최대 3회)
            success = False
            for attempt in range(3):
                try:
                    worksheet = get_worksheet()
                    if worksheet:
                        # Google Sheets에 행 추가
                        worksheet.append_row(new_row)
                        success = True
                        break
                except Exception as e:
                    if attempt < 2:
                        st.warning(f"⚠️ 저장 시도 {attempt + 1}/3 실패, 다시 시도 중...")
                        import time
                        time.sleep(1)
                    else:
                        st.error(f"🚨 저장 실패 (3회 시도): {str(e)}")
            
            if success:
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

# ===== TAB 3: 상담일지 조회 =====
with tab3:
    st.header("🔍 상담일지 조회")
    
    # 조회 방식 선택
    col1, col2 = st.columns([4, 1])
    with col1:
        search_type = st.radio("조회 방식을 선택하세요:", ["기간선택", "환자검색"], horizontal=True)
    with col2:
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()
    
    if search_type == "기간선택":
        st.subheader("📅 기간 선택")
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            consultant_filter = st.selectbox("👤 상담자", ["전체", "우다혜", "전누리", "임예린"], key="tab2_consultant")
        with col2:
            start_date = st.date_input("시작일", datetime.now().date(), key="tab2_start")
        with col3:
            end_date = st.date_input("종료일", datetime.now().date(), key="tab2_end")
        
        # 데이터 로드 및 필터링
        df = load_all_data()
        
        if not df.empty:
            # 날짜 필터링
            df['날짜'] = pd.to_datetime(df['날짜'])
            start_date_str = pd.to_datetime(start_date)
            end_date_str = pd.to_datetime(end_date)
            
            filtered_df = df[(df['날짜'] >= start_date_str) & (df['날짜'] <= end_date_str)]
            
            # 상담자 필터링
            if consultant_filter != "전체":
                filtered_df = filtered_df[filtered_df['상담자'] == consultant_filter]
            
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

# ===== TAB 4: 상담 보고 =====
with tab4:
    st.header("📊 상담 보고")
    
    # 상담자 선택 및 기간 선택
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        selected_consultant = st.selectbox("👤 상담자 선택", ["전체", "우다혜", "전누리", "임예린"], key="tab3_consultant")
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
        if selected_consultant == "전체":
            filtered_df = df[(df['날짜'] >= start_date_str) & (df['날짜'] <= end_date_str)]
        else:
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
                    
                    cons_count = len(consultant_data)
                    cons_confirmed = len(consultant_data[consultant_data['상담결과'] == '확정']) if cons_count > 0 else 0
                    cons_unconfirmed = len(consultant_data[consultant_data['상담결과'] == '미확정']) if cons_count > 0 else 0
                    cons_rate = (cons_confirmed / cons_count * 100) if cons_count > 0 else 0
                    
                    if cons_count > 0:
                        consultant_data['금액_숫자'] = pd.to_numeric(consultant_data['금액'], errors='coerce').fillna(0)
                        cons_confirmed_amount = int(consultant_data[consultant_data['상담결과'] == '확정']['금액_숫자'].sum())
                        cons_unconfirmed_amount = int(consultant_data[consultant_data['상담결과'] == '미확정']['금액_숫자'].sum())
                    else:
                        cons_confirmed_amount = 0
                        cons_unconfirmed_amount = 0
                    
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
                
                # 확정매출로 정렬 (높은 순)
                consultant_df['확정매출_숫자'] = consultant_df['확정매출'].str.replace(',', '').astype(int)
                consultant_df = consultant_df.sort_values('확정매출_숫자', ascending=False).drop('확정매출_숫자', axis=1)
                
                st.dataframe(consultant_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # ===== 분류별 상담 현황 =====
            st.subheader("📂 분류별 상담 현황")
            
            # 분류별 통계
            category_stats = []
            for category in ["예약 신환", "미예약 신환", "예약 구환", "미예약 구환"]:
                category_data = filtered_df[filtered_df['분류'] == category]
                confirmed = len(category_data[category_data['상담결과'] == '확정'])
                unconfirmed = len(category_data[category_data['상담결과'] == '미확정'])
                
                category_stats.append({
                    "분류": category,
                    "확정": confirmed,
                    "미확정": unconfirmed
                })
            
            category_df = pd.DataFrame(category_stats)
            st.dataframe(category_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # ===== 상담일지 =====
            st.subheader("📝 상담일지")
            
            # 역순으로 정렬 (최신순)
            report_filtered_df = filtered_df.iloc[::-1]
            
            if not report_filtered_df.empty:
                st.info(f"✅ {len(report_filtered_df)}건의 상담 기록")
                
                # 상담 내용 상세 표시
                for idx, row in report_filtered_df.iterrows():
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
            st.info(f"⚠️ 해당 기간에 상담 기록이 없습니다.")
    else:
        st.info("📭 저장된 상담 기록이 없습니다.")

# ===== TAB 2: 미확정 리마인더 =====
with tab2:
    st.header("📞 미확정 리마인더")
    
    # 상담자 선택
    col1, col2 = st.columns([2, 4])
    with col1:
        reminder_consultant = st.selectbox("👤 상담자 선택", ["전체", "우다혜", "전누리", "임예린"], key="tab4_consultant")
    
    # 데이터 로드
    df = load_all_data()
    
    if not df.empty:
        # 날짜 변환
        df['날짜'] = pd.to_datetime(df['날짜'])
        
        # 미확정만 필터링
        unconfirmed_df = df[df['상담결과'] == '미확정'].copy()
        
        # 상담자 필터링
        if reminder_consultant != "전체":
            unconfirmed_df = unconfirmed_df[unconfirmed_df['상담자'] == reminder_consultant]
        
        if not unconfirmed_df.empty:
            # 경과일 계산
            today = pd.to_datetime(datetime.now().date())
            unconfirmed_df['경과일'] = (today - unconfirmed_df['날짜']).dt.days
            
            # 7일 이상 경과한 것만 필터링
            recall_df = unconfirmed_df[unconfirmed_df['경과일'] >= 7].copy()
            
            if not recall_df.empty:
                recall_count = len(recall_df)
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"### 🔴 리콜 필요 ({recall_count}명)")
                
                st.divider()
                
                # 최신순으로 정렬
                recall_df = recall_df.sort_values('날짜', ascending=False)
                
                # 상담 기록 표시
                for idx, row in recall_df.iterrows():
                    # expander 제목에 간단한 정보
                    with st.expander(f"👤 {row['환자성함']} | 차트: {row['차트번호']} | {row['경과일']}일 경과 | {int(float(row['금액'])) if pd.notnull(row['금액']) else 0:,}원 | 미확정 | {row['상담자']}", expanded=True):
                        # 상세 내용
                        st.write(f"**주요포인트:** {row['주요포인트']}")
                        st.write(f"**상담내용:** {row['상담내용']}")
                        
                        st.divider()
                        
                        # 리콜 버튼
                        if st.button("✅ 리콜완료", key=f"recall_btn_{idx}", use_container_width=True):
                            # 버튼 클릭 시 바로 Google Sheets에 리콜상태 업데이트
                            st.session_state[f"show_confirm_{idx}"] = True
                        
                        # 확인 메시지 표시
                        if st.session_state.get(f"show_confirm_{idx}", False):
                            st.warning(f"❓ {row['환자성함']} (차트: {row['차트번호']})의 리콜을 완료하시겠습니까?")
                            
                            col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
                            with col2:
                                if st.button("✅ 확인", key=f"confirm_{idx}", use_container_width=True):
                                    # Google Sheets에 리콜상태 업데이트
                                    try:
                                        worksheet = get_worksheet()
                                        if worksheet:
                                            # 모든 데이터 가져오기
                                            data = worksheet.get_all_records()
                                            
                                            # 해당 행 찾기
                                            for i, record in enumerate(data):
                                                if (record.get('환자성함') == row['환자성함'] and 
                                                    record.get('차트번호') == row['차트번호'] and
                                                    record.get('날짜') == row['날짜'].strftime('%Y-%m-%d')):
                                                    # 리콜상태 업데이트
                                                    worksheet.update_cell(i + 2, 11, "리콜완료")
                                                    st.session_state[f"show_confirm_{idx}"] = False
                                                    st.success(f"✅ {row['환자성함']}의 리콜이 완료되었습니다!")
                                                    st.rerun()
                                                    break
                                    except Exception as e:
                                        st.error(f"🚨 리콜 완료 중 에러: {str(e)}")
                            with col3:
                                if st.button("❌ 취소", key=f"cancel_{idx}", use_container_width=True):
                                    st.session_state[f"show_confirm_{idx}"] = False
                                    st.rerun()
            else:
                st.success("✅ 리콜이 필요한 환자가 없습니다!")
        else:
            st.info("📭 미확정 상담 기록이 없습니다.")
        
        # ===== 리콜 완료 목록 =====
        st.markdown("---")
        st.subheader("✅ 리콜 완료 목록")
        
        # 리콜 완료된 것만 필터링 (리콜상태가 '리콜완료'인 것)
        recall_completed_df = df[(df['리콜상태'] == '리콜완료')].copy()
        
        # 상담자 필터링
        if reminder_consultant != "전체":
            recall_completed_df = recall_completed_df[recall_completed_df['상담자'] == reminder_consultant]
        
        if not recall_completed_df.empty:
            completed_count = len(recall_completed_df)
            st.info(f"🎉 {completed_count}명의 리콜이 완료되었습니다.")
            
            # 역순으로 정렬
            recall_completed_df = recall_completed_df.sort_values('날짜', ascending=False)
            
            # 완료된 상담 기록 표시
            for idx, row in recall_completed_df.iterrows():
                with st.expander(f"✅ {row['환자성함']} | 차트: {row['차트번호']} | {row['상담자']} | 완료"):
                    # 정보 표시
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.write(f"**환자명:** {row['환자성함']}")
                    with col2:
                        st.write(f"**분류:** {row['분류']}")
                    with col3:
                        st.write(f"**진단원장:** {row['진단원장']}")
                    with col4:
                        st.write(f"**상담일:** {row['날짜'].strftime('%Y-%m-%d')}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        try:
                            amount = int(float(row['금액']))
                            st.write(f"**금액:** {amount:,}원")
                        except:
                            st.write(f"**금액:** {row['금액']}")
                    with col2:
                        st.write(f"**주요포인트:** {row['주요포인트']}")
                    
                    st.write("---")
                    st.write(f"**상담내용:** {row['상담내용']}")
        else:
            st.info("📭 리콜 완료 기록이 없습니다.")
    else:
        st.info("📭 저장된 상담 기록이 없습니다.")

# 하단 로그아웃
st.divider()
if st.button("🔓 로그아웃"):
    st.session_state.logged_in = False
    st.rerun()
