import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime, timedelta
import re
import uuid
import plotly.express as px
import plotly.graph_objects as go
from calendar import monthrange

CLINIC_NAME = "더뉴치과"
LOGIN_PASSWORD = "7620"      # 로그인 비밀번호
STATS_PASSWORD = "9796"      # 📈 통계 탭 비밀번호
CONSULT_SHEET_NAME = "상담일지"  # 상담일지 데이터가 있는 시트(탭) 이름
RECALL_AFTER_DAYS = 7        # 미확정 후 며칠이 지나면 리콜 대상으로 보여줄지

st.set_page_config(page_title=f"{CLINIC_NAME} 상담일지", layout="wide")

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

# ===== 📄 시트 컬럼 =====
# 시트에 저장/수정할 때는 "컬럼 순서"가 아니라 시트 1행의 "컬럼 이름"을 기준으로 씁니다.
# 기존 더뉴치과 시트에는 "고유ID" 컬럼이 없으므로, 앱이 처음 실행될 때
# 맨 오른쪽 끝(L열)에 "고유ID" 컬럼을 자동으로 추가하고 기존 기록에 ID를 채워 넣습니다.
# (기존 A~K열 데이터는 전혀 옮기거나 바꾸지 않습니다)
SPREADSHEET_HEADER = [
    "날짜", "상담자", "진단원장", "환자성함", "차트번호", "분류",
    "상담결과", "금액", "주요포인트", "상담내용", "리콜상태", "고유ID"
]

COUNSELORS = ["우다혜", "전누리", "임예린"]
DOCTORS = ["김동현 원장", "김언형 원장", "정성영 원장", "박경리 원장", "권영은 원장"]

# ===== ⚠️ 컴플레인 관리용 시트 컬럼/옵션 =====
# 같은 Google Sheets 파일 안에 "컴플레인"이라는 새 시트(탭)를 만들어서 별도로 관리합니다.
COMPLAINT_HEADER = [
    "고유ID", "날짜", "환자성함", "차트번호", "담당자", "유형",
    "상세내용", "처리상태", "처리내용", "처리일", "기록자", "처리자"
]
COMPLAINT_STAFF_OPTIONS = COUNSELORS + DOCTORS
COMPLAINT_TYPES = ["진료결과", "응대", "비용", "대기시간", "예약", "기타"]
COMPLAINT_STATUSES = ["접수", "처리중", "완료"]

# ===== 📋 Helper Functions (반복 코드 제거) =====
def format_amount(value):
    """금액을 정수로 변환. '300,000', '30000원', 빈칸 같은 값도 에러 없이 처리 (실패 시 0)"""
    try:
        text = str(value).replace(",", "").replace("원", "").strip()
        if text == "" or text.lower() in ("nan", "none"):
            return 0
        return int(float(text))
    except (ValueError, TypeError):
        return 0

def format_chart_no(value):
    """차트번호 포맷팅 (12345.0 → 12345, 숫자가 아닌 차트번호는 그대로 표시)"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    try:
        return str(int(float(text)))
    except (ValueError, TypeError):
        return text

def filter_by_date_range(df, start_date, end_date):
    """날짜 범위로 데이터 필터링"""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    return df[(df['날짜'] >= start_str) & (df['날짜'] <= end_str)].copy()

def safe_parse_date(value):
    """문자열 날짜를 date 객체로 안전하게 변환 (실패 시 None 반환)"""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def calculate_stats(df):
    """통계 계산"""
    df['금액_숫자'] = df['금액'].apply(format_amount)

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

        confirmed_amount = int(counselor_data[counselor_data['상담결과'] == '확정']['금액_숫자'].sum())
        unconfirmed_amount = int(counselor_data[counselor_data['상담결과'] == '미확정']['금액_숫자'].sum())

        agreement_rate = (confirmed / total_count * 100) if total_count > 0 else 0

        counselor_stats_list.append({
            '상담자': counselor,
            '상담건수': total_count,
            '확정건수': confirmed,
            '미확정건수': unconfirmed,
            '동의율': f"{agreement_rate:.1f}%",
            '확정매출_숫자': confirmed_amount,
            '확정매출': f"{confirmed_amount:,}원",
            '미확정매출': f"{unconfirmed_amount:,}원"
        })

    result_df = pd.DataFrame(counselor_stats_list)
    result_df = result_df.sort_values('확정매출_숫자', ascending=False)
    result_df = result_df.drop('확정매출_숫자', axis=1)

    return result_df.reset_index(drop=True)
def render_consultation_detail(row, key_prefix):
    """상담 상세 내용을 보여주는 공통 렌더링 함수 (조회/보고 탭에서 중복 제거)"""
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write(f"**분류:** {row.get('분류', '')}")
        st.write(f"**금액:** {format_amount(row.get('금액')):,}원")
    with col2:
        st.write(f"**진단원장:** {row.get('진단원장', '')}")
        st.write(f"**차트번호:** {format_chart_no(row.get('차트번호'))}")
    with col3:
        result = row.get('상담결과', '')
        color = 'blue' if result == '확정' else 'red'
        st.markdown(f"**상담결과:** <span style='color:{color}; font-weight:bold;'>{result}</span>", unsafe_allow_html=True)

    st.markdown(f"**주요포인트:** {row.get('주요포인트', '')}")
    st.markdown(f"**상담내용:**\n\n{row.get('상담내용', '')}")


# ===== 🔌 Google Sheets 연결 (gspread 직접 사용) =====
# 새 상담 저장은 append_row로 "새 행만" 추가하고, 기존 기록 수정은 고유ID로 그 행만
# 콕 집어 update_cell 하기 때문에 여러 명이 동시에 사용해도 서로 데이터를 덮어쓸 위험이 없습니다.
# (기존 방식은 전체 시트를 읽어서 통째로 다시 쓰는 방식이라 동시 저장 시 유실 위험이 있었습니다)

@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    """서비스 계정 인증으로 스프레드시트 전체 객체를 가져옵니다. secrets.toml의 [connections.gsheets]를
    그대로 사용하므로 기존 secrets 설정을 바꿀 필요는 없습니다."""
    gs_secrets = dict(st.secrets["connections"]["gsheets"])
    spreadsheet = str(gs_secrets.pop("spreadsheet")).strip()
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(gs_secrets, scopes=scopes)
    gc = gspread.authorize(creds)
    # secrets의 spreadsheet 값이 URL이든 시트 ID(key)든 둘 다 동작하도록 처리
    if spreadsheet.startswith("http"):
        return gc.open_by_url(spreadsheet)
    return gc.open_by_key(spreadsheet)


def ensure_columns(ws, required_cols):
    """시트 1행(헤더)에 없는 컬럼이 있으면 기존 데이터는 그대로 두고 오른쪽 끝에만 추가.
    시트의 실제 헤더 목록을 반환합니다."""
    header = ws.row_values(1)
    missing = [c for c in required_cols if c not in header]
    if missing:
        needed_cols = len(header) + len(missing)
        if ws.col_count < needed_cols:
            ws.add_cols(needed_cols - ws.col_count)
        start_cell = gspread.utils.rowcol_to_a1(1, len(header) + 1)
        ws.update(range_name=start_cell, values=[missing])
        header = header + missing
    return header


def backfill_unique_ids(ws, header):
    """고유ID가 비어 있는 기존 기록(예전 앱으로 저장된 행)에 고유ID를 채워 넣습니다.
    고유ID 칸만 쓰고, 다른 칸은 건드리지 않습니다."""
    id_col = header.index("고유ID") + 1
    name_col = header.index("환자성함") + 1
    ids = ws.col_values(id_col)
    names = ws.col_values(name_col)
    updates = []
    for row_num in range(2, len(names) + 1):
        has_name = str(names[row_num - 1]).strip() != ""
        has_id = row_num <= len(ids) and str(ids[row_num - 1]).strip() != ""
        if has_name and not has_id:
            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_num, id_col),
                "values": [[str(uuid.uuid4())]],
            })
    if updates:
        ws.batch_update(updates)
    return len(updates)


@st.cache_resource(show_spinner=False)
def get_worksheet():
    """상담일지 데이터가 있는 시트. 고유ID 컬럼이 없으면 자동으로 추가하고 기존 기록에 ID를 채웁니다."""
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(CONSULT_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.sheet1
    header = ensure_columns(ws, SPREADSHEET_HEADER)
    backfill_unique_ids(ws, header)
    return ws


@st.cache_resource(show_spinner=False)
def get_sheet_header(_ws, sheet_title):
    """시트의 실제 헤더(1행)를 가져옵니다. 저장/수정 시 컬럼 위치를 찾는 데 사용합니다."""
    return _ws.row_values(1)


@st.cache_resource(show_spinner=False)
def get_complaint_worksheet():
    """컴플레인 기록용 시트. "컴플레인"이라는 이름의 탭이 없으면 자동으로 새로 만듭니다.
    이미 있는데 컬럼이 나중에 추가된 경우(예: 기록자/처리자), 기존 데이터는 그대로 두고
    새 컬럼만 헤더 오른쪽 끝에 자동으로 추가합니다."""
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet("컴플레인")
        ensure_columns(ws, COMPLAINT_HEADER)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="컴플레인", rows=2000, cols=len(COMPLAINT_HEADER))
        ws.append_row(COMPLAINT_HEADER, value_input_option="USER_ENTERED")
    return ws


@st.cache_data(ttl=30, show_spinner=False)
def load_gsheet_data(_ws):
    """Google Sheet에서 데이터 로드 (30초 캐시 - 저장/수정 직후에는 캐시를 즉시 비워서 최신 상태를 보여줍니다)"""
    try:
        records = _ws.get_all_records()
        # 예전 앱으로 저장되어 고유ID가 없는 기록이 새로 생겼다면 ID를 채우고 다시 읽기
        if any(str(r.get('환자성함', '')).strip() and not str(r.get('고유ID', '')).strip() for r in records):
            header = get_sheet_header(_ws, _ws.title)
            if "고유ID" in header and backfill_unique_ids(_ws, header):
                records = _ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(columns=SPREADSHEET_HEADER)

        for col in SPREADSHEET_HEADER:
            if col not in df.columns:
                df[col] = '미리콜' if col == '리콜상태' else ''

        df = df.dropna(subset=["환자성함"]).copy()
        df = df[df['환자성함'].astype(str).str.strip() != ''].copy()

        df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce').dt.strftime('%Y-%m-%d')
        df['날짜'] = df['날짜'].fillna('')
        df['리콜상태'] = df['리콜상태'].fillna('미리콜').replace('', '미리콜')
        df['고유ID'] = df['고유ID'].astype(str).replace('nan', '')

        return df
    except Exception:
        st.warning("⚠️ Google Sheets 연결 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        return pd.DataFrame(columns=SPREADSHEET_HEADER)


def append_row_generic(ws, record: dict):
    """레코드 한 개를 시트 맨 끝에 한 행만 추가 (기존 행은 전혀 건드리지 않음).
    시트의 실제 헤더 순서에 맞춰 값을 배치합니다."""
    header = get_sheet_header(ws, ws.title)
    row = [str(record.get(col, "")) for col in header]
    # table_range="A1": 시트 오른쪽에 빈 칸이 있어도 항상 A열부터 새 행이 붙도록 고정
    ws.append_row(row, value_input_option="USER_ENTERED", table_range="A1")


def update_fields_generic(ws, unique_id: str, updates: dict) -> bool:
    """고유ID로 해당 행을 찾아 지정한 컬럼(들)만 정확히 수정. 다른 행/컬럼은 건드리지 않음."""
    if not unique_id:
        return False
    header = get_sheet_header(ws, ws.title)
    try:
        id_col_num = header.index("고유ID") + 1
        cell = ws.find(unique_id, in_column=id_col_num)
    except Exception:
        cell = None
    if cell is None:
        return False
    for col_name, value in updates.items():
        col_num = header.index(col_name) + 1
        ws.update_cell(cell.row, col_num, str(value))
    return True


def append_record(ws, record: dict):
    """상담일지 시트에 새 기록 추가"""
    append_row_generic(ws, record)


def update_record_fields(ws, unique_id: str, updates: dict) -> bool:
    """상담일지 시트에서 지정한 컬럼(들)만 수정"""
    return update_fields_generic(ws, unique_id, updates)


def append_complaint(ws, record: dict):
    """컴플레인 시트에 새 기록 추가"""
    append_row_generic(ws, record)


def update_complaint_fields(ws, unique_id: str, updates: dict) -> bool:
    """컴플레인 시트에서 지정한 컬럼(들)만 수정"""
    return update_fields_generic(ws, unique_id, updates)


@st.cache_data(ttl=30, show_spinner=False)
def load_complaint_data(_ws):
    """컴플레인 시트에서 데이터 로드 (30초 캐시, 저장/수정 직후에는 캐시를 즉시 비워서 최신 상태를 보여줍니다)"""
    try:
        records = _ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(columns=COMPLAINT_HEADER)

        for col in COMPLAINT_HEADER:
            if col not in df.columns:
                df[col] = '접수' if col == '처리상태' else ''

        df = df.dropna(subset=["환자성함"]).copy()
        df = df[df['환자성함'].astype(str).str.strip() != ''].copy()

        df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce').dt.strftime('%Y-%m-%d')
        df['날짜'] = df['날짜'].fillna('')
        df['처리상태'] = df['처리상태'].replace('', '접수')
        df['고유ID'] = df['고유ID'].astype(str).replace('nan', '')

        return df
    except Exception:
        st.warning("⚠️ Google Sheets 연결 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        return pd.DataFrame(columns=COMPLAINT_HEADER)


# ===== 🔒 로그인 기능 (기존 방식 유지) =====
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown(f"<h1 style='text-align: center;'>🔐 {CLINIC_NAME} 상담일지</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>비밀번호를 입력하세요</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            password = st.text_input("🔑 비밀번호", type="password", placeholder="비밀번호 입력")
            submitted = st.form_submit_button("🔓 로그인", use_container_width=True)

            if submitted:
                if password == LOGIN_PASSWORD:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("❌ 비밀번호가 틀렸습니다. 다시 입력해주세요.")
    st.stop()

# ===== 로그인 성공 후 앱 시작 =====
header_col1, header_col2 = st.columns([5, 1])
with header_col1:
    st.title(f"📂 {CLINIC_NAME} 상담일지")
with header_col2:
    st.write("")
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.stats_unlocked = False
        st.rerun()

ws = get_worksheet()

# 데이터 로드
df = load_gsheet_data(ws)

# ===== 6개 탭 생성 =====
tabs_list = st.tabs([
    "📝 상담일지 작성",
    "📞 미확정 리마인더",
    "⚠️ 컴플레인 관리",
    "🔍 상담일지 조회/수정",
    "📊 보고 자료",
    "📈 통계"
])

tab_write = tabs_list[0]       # 상담일지 작성
tab_reminder = tabs_list[1]    # 미확정 리마인더
tab_complaint = tabs_list[2]   # 컴플레인 관리
tab_edit = tabs_list[3]        # 상담일지 조회/수정
tab_summary = tabs_list[4]     # 보고 자료
tab_statistics = tabs_list[5]  # 통계

# ===== TAB 1: 상담일지 작성 =====
with tab_write:
    st.header("📝 상담일지 작성")

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

    submitted = st.button("💾 저장하기", use_container_width=True)

    if submitted:
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
            new_record = {
                "고유ID": str(uuid.uuid4()),
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
            }
            try:
                append_record(ws, new_record)
                load_gsheet_data.clear()  # 캐시 무효화 → 다음 조회 시 최신 데이터 반영

                st.success("✅ 저장되었습니다!", icon="✅")
                st.balloons()

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

                # 입력한 날짜의 내역 (방금 저장한 내용을 화면에서 바로 보여주기 위해, 기존 df에 새 기록만 더해 표시)
                st.subheader("📋 입력 날짜 내역")
                selected_day = input_date.strftime("%Y-%m-%d")
                today_data = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
                today_data = today_data[today_data['날짜'] == selected_day].copy()

                if not today_data.empty:
                    today_data = today_data.iloc[::-1]
                    st.write(f"총 **{len(today_data)}건** 입력됨")

                    for idx, row in today_data.iterrows():
                        with st.expander(f"📌 {row['환자성함']} - {row['상담자']} ({row['상담결과']})"):
                            render_consultation_detail(row, key_prefix=f"just_saved_{idx}")

                st.divider()
                st.info("✏️ 다음 항목을 입력하기 시작하시면 위 입력칸들은 자동으로 초기화됩니다")

                # 다음 입력을 위해 폼 내용 초기화 (위젯 키를 지우면 다음 렌더링에서 빈 값으로 다시 시작함)
                # (이미 화면에 그려진 입력칸에 값을 "대입"하면 Streamlit 오류가 나므로, 키를 지우는 방식만 사용)
                for k in ["tab1_name", "tab1_chart", "tab1_points", "tab1_content",
                          "tab1_counselor", "tab1_doctor", "tab1_result", "tab1_amount"]:
                    st.session_state.pop(k, None)
            except Exception:
                st.error("❌ 저장 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

# ===== TAB 2: 미확정 리마인더 =====
with tab_reminder:
    st.header("📞 미확정 리마인더")
    st.caption(f"미확정으로 저장된 지 {RECALL_AFTER_DAYS}일 이상 지난 환자 중, 아직 리콜하지 않은 환자를 보여줍니다.")

    col1, col2 = st.columns([2, 4])
    with col1:
        reminder_counselor = st.selectbox("👤 상담자 선택", ["전체"] + COUNSELORS, key="reminder_counselor")

    df_reminder_source = load_gsheet_data(ws)

    if st.session_state.get("recall_done_msg"):
        st.success(st.session_state.pop("recall_done_msg"))

    if df_reminder_source.empty:
        st.info("📭 저장된 상담 기록이 없습니다.")
    else:
        df_rem = df_reminder_source.copy()
        if reminder_counselor != "전체":
            df_rem = df_rem[df_rem['상담자'] == reminder_counselor]

        today_ts = pd.Timestamp(datetime.now().date())
        df_rem['경과일'] = (today_ts - pd.to_datetime(df_rem['날짜'], errors='coerce')).dt.days

        # 리콜 필요: 미확정 + 아직 리콜 안 함 + N일 이상 경과
        recall_df = df_rem[
            (df_rem['상담결과'] == '미확정') &
            (df_rem['리콜상태'] != '리콜완료') &
            (df_rem['경과일'] >= RECALL_AFTER_DAYS)
        ].sort_values('날짜', ascending=False)

        if recall_df.empty:
            st.success("✅ 리콜이 필요한 환자가 없습니다!")
        else:
            st.markdown(f"### 🔴 리콜 필요 ({len(recall_df)}명)")
            st.divider()

            for idx, row in recall_df.iterrows():
                unique_id = row.get('고유ID', '')
                row_key = unique_id or f"idx{idx}"
                title = (
                    f"👤 {row['환자성함']} | 차트: {format_chart_no(row['차트번호'])} | "
                    f"{int(row['경과일'])}일 경과 | {format_amount(row['금액']):,}원 | {row['상담자']}"
                )
                with st.expander(title, expanded=True):
                    st.write(f"**상담일:** {row['날짜']}  |  **진단원장:** {row['진단원장']}  |  **분류:** {row['분류']}")
                    st.write(f"**주요포인트:** {row['주요포인트']}")
                    st.write(f"**상담내용:** {row['상담내용']}")

                    if not unique_id:
                        st.warning("⚠️ 이 기록은 고유ID가 없어 리콜완료 처리를 할 수 없습니다. 잠시 후 새로고침해주세요.")
                        continue

                    confirm_key = f"recall_confirm_{row_key}"
                    if not st.session_state.get(confirm_key, False):
                        if st.button("✅ 리콜완료", key=f"recall_btn_{row_key}", use_container_width=True):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning(f"❓ {row['환자성함']} 환자의 리콜을 완료 처리하시겠습니까?")
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            if st.button("✅ 확인", key=f"recall_ok_{row_key}", use_container_width=True):
                                try:
                                    if update_record_fields(ws, unique_id, {"리콜상태": "리콜완료"}):
                                        load_gsheet_data.clear()
                                        st.session_state.pop(confirm_key, None)
                                        st.session_state["recall_done_msg"] = f"✅ {row['환자성함']} 환자의 리콜이 완료되었습니다!"
                                        st.rerun()
                                    else:
                                        st.error("❌ 해당 기록을 찾지 못했습니다. 새로고침 후 다시 시도해주세요.")
                                except Exception:
                                    st.error("❌ 저장 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
                        with cc2:
                            if st.button("❌ 취소", key=f"recall_cancel_{row_key}", use_container_width=True):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

        # ===== 리콜 완료 목록 =====
        st.divider()
        st.subheader("✅ 리콜 완료 목록")
        done_df = df_rem[df_rem['리콜상태'] == '리콜완료'].sort_values('날짜', ascending=False)
        if done_df.empty:
            st.info("📭 리콜 완료 기록이 없습니다.")
        else:
            st.info(f"🎉 {len(done_df)}명의 리콜이 완료되었습니다.")
            for idx, row in done_df.iterrows():
                with st.expander(f"✅ {row['날짜']} - {row['환자성함']} (차트: {format_chart_no(row['차트번호'])}) - {row['상담자']}"):
                    render_consultation_detail(row, key_prefix=f"recall_done_{idx}")

# ===== TAB 3: 컴플레인 관리 =====
with tab_complaint:
    try:
        st.header("⚠️ 컴플레인 관리")

        complaint_ws = get_complaint_worksheet()

        st.subheader("📝 컴플레인 등록")
        with st.form("complaint_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                c_date = st.date_input("📅 발생일", datetime.now().date(), key="complaint_date")
            with col2:
                c_name = st.text_input("👤 환자 성함", key="complaint_name")
            with col3:
                c_chart_no = st.text_input("🔢 차트 번호", key="complaint_chart")

            col4, col5, col6 = st.columns(3)
            with col4:
                c_staff = st.selectbox(
                    "👤 관련 담당자", [None] + COMPLAINT_STAFF_OPTIONS,
                    format_func=lambda x: "선택하세요" if x is None else x, key="complaint_staff"
                )
            with col5:
                c_type = st.selectbox("🏷️ 유형", COMPLAINT_TYPES, key="complaint_type")
            with col6:
                c_recorder = st.selectbox(
                    "✍️ 기록자", [None] + COMPLAINT_STAFF_OPTIONS,
                    format_func=lambda x: "선택하세요" if x is None else x, key="complaint_recorder"
                )

            c_content = st.text_area("💬 상세 내용", height=120, key="complaint_content")

            c_submitted = st.form_submit_button("💾 컴플레인 등록", use_container_width=True)

        if st.session_state.pop("complaint_just_saved", False):
            st.success("✅ 컴플레인이 등록되었습니다!")

        if c_submitted:
            if not c_name:
                st.error("❌ 환자 성함을 입력해주세요!")
            elif not c_content or not c_content.strip():
                st.error("❌ 상세 내용을 입력해주세요!")
            elif c_recorder is None:
                st.error("❌ 기록자를 선택해주세요!")
            else:
                new_complaint = {
                    "고유ID": str(uuid.uuid4()),
                    "날짜": c_date.strftime("%Y-%m-%d"),
                    "환자성함": c_name,
                    "차트번호": c_chart_no,
                    "담당자": c_staff or "",
                    "유형": c_type,
                    "상세내용": c_content,
                    "처리상태": "접수",
                    "처리내용": "",
                    "처리일": "",
                    "기록자": c_recorder,
                    "처리자": ""
                }
                try:
                    append_complaint(complaint_ws, new_complaint)
                    load_complaint_data.clear()
                    st.session_state["complaint_just_saved"] = True
                    st.rerun()
                except Exception:
                    st.error("❌ 등록 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

        st.divider()

        st.subheader("📋 컴플레인 목록")
        df_complaints = load_complaint_data(complaint_ws)

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            status_filter = st.selectbox("처리상태 필터", ["전체"] + COMPLAINT_STATUSES, key="complaint_status_filter")
        with col_f2:
            search_term = st.text_input("환자 이름/차트번호 검색", key="complaint_search")

        if not df_complaints.empty:
            df_view = df_complaints.copy()
            if status_filter != "전체":
                df_view = df_view[df_view['처리상태'] == status_filter]
            if search_term:
                df_view = df_view[
                    (df_view['환자성함'].str.contains(search_term, case=False, na=False)) |
                    (df_view['차트번호'].astype(str).str.contains(search_term, case=False, na=False))
                ]

            df_view = df_view.sort_values('날짜', ascending=False)

            if df_view.empty:
                st.info("조건에 맞는 컴플레인이 없습니다.")
            else:
                status_icons = {"접수": "🔴", "처리중": "🟡", "완료": "🟢"}
                for idx, row in df_view.iterrows():
                    unique_id = row.get('고유ID', '')
                    row_key = unique_id or f"idx{idx}"
                    icon = status_icons.get(row['처리상태'], "⚪")
                    with st.expander(
                        f"{icon} {row['날짜']} - {row['환자성함']} ({row['유형']}) - {row['처리상태']}",
                        expanded=(row['처리상태'] != '완료')
                    ):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**차트번호:** {format_chart_no(row['차트번호'])}")
                            st.write(f"**관련 담당자:** {row['담당자']}")
                            st.write(f"**유형:** {row['유형']}")
                            st.write(f"**기록자:** {row.get('기록자', '')}")
                        with col2:
                            st.write(f"**발생일:** {row['날짜']}")
                            st.write(f"**현재 상태:** {row['처리상태']}")
                            if row['처리일']:
                                st.write(f"**처리일:** {row['처리일']}")
                            if row.get('처리자'):
                                st.write(f"**처리자:** {row['처리자']}")

                        st.markdown(f"**상세 내용:**\n\n{row['상세내용']}")

                        if not unique_id:
                            st.warning("⚠️ 이 기록은 고유ID가 없어 수정할 수 없습니다.")
                        else:
                            st.write("**처리 상태/내용 업데이트:**")
                            current_status = row['처리상태'] if row['처리상태'] in COMPLAINT_STATUSES else COMPLAINT_STATUSES[0]
                            new_status = st.selectbox(
                                "처리상태 변경",
                                COMPLAINT_STATUSES,
                                index=COMPLAINT_STATUSES.index(current_status),
                                key=f"complaint_status_{row_key}"
                            )
                            current_handler = row.get('처리자', '') or None
                            new_handler = st.selectbox(
                                "처리자",
                                [None] + COMPLAINT_STAFF_OPTIONS,
                                index=(COMPLAINT_STAFF_OPTIONS.index(current_handler) + 1) if current_handler in COMPLAINT_STAFF_OPTIONS else 0,
                                format_func=lambda x: "선택하세요" if x is None else x,
                                key=f"complaint_handler_{row_key}"
                            )
                            new_note = st.text_area(
                                "처리내용",
                                value=row.get('처리내용', ''),
                                key=f"complaint_note_{row_key}"
                            )

                            if st.button("✅ 저장", key=f"complaint_save_{row_key}"):
                                updates = {}
                                if new_status != row['처리상태']:
                                    updates["처리상태"] = new_status
                                    if new_status == "완료":
                                        updates["처리일"] = datetime.now().date().strftime("%Y-%m-%d")
                                if new_note != row.get('처리내용', ''):
                                    updates["처리내용"] = new_note
                                if (new_handler or '') != (row.get('처리자', '') or ''):
                                    updates["처리자"] = new_handler or ''

                                if updates:
                                    try:
                                        if update_complaint_fields(complaint_ws, unique_id, updates):
                                            load_complaint_data.clear()
                                            st.success("✅ 저장되었습니다!")
                                            st.rerun()
                                        else:
                                            st.error("❌ 해당 기록을 찾지 못했습니다. 새로고침 후 다시 시도해주세요.")
                                    except Exception:
                                        st.error("❌ 저장 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
                                else:
                                    st.info("변경된 내용이 없습니다.")
        else:
            st.info("등록된 컴플레인이 없습니다.")
    except Exception as e:
        st.error("❌ 컴플레인 탭에서 오류가 발생했습니다.")
        with st.expander("오류 자세히 보기 (문제 파악용)"):
            st.code(str(e))

# ===== TAB 4: 상담일지 조회/수정 =====
with tab_edit:
    st.header("🔍 상담일지 조회/수정")

    df_edit_source = load_gsheet_data(ws)

    if not df_edit_source.empty:
        st.write("환자 이름 또는 차트번호로 검색하세요. (부분 검색 가능)")
        search_patient = st.text_input("🔍 환자 이름 또는 차트번호 검색", placeholder="예: 송호선, 12345 등", key="tab_edit_search")

        if search_patient:
            df_search = df_edit_source[
                (df_edit_source['환자성함'].str.contains(search_patient, case=False, na=False)) |
                (df_edit_source['차트번호'].astype(str).str.contains(search_patient, case=False, na=False))
            ].copy()

            if not df_search.empty:
                st.success(f"✅ '{search_patient}' 검색 결과: {len(df_search)}건")
                st.divider()

                for idx, row in df_search.iterrows():
                    chart_num = format_chart_no(row['차트번호'])
                    unique_id = row.get('고유ID', '')
                    row_key = unique_id or f"idx{idx}"
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
                            current_result = row['상담결과']
                            st.write(f"**현재 상담결과:** {current_result}")
                            st.write("**상담결과 수정:**")
                            new_result = st.selectbox(
                                "변경할 상담결과 선택",
                                ["확정", "미확정"],
                                index=0 if current_result == "확정" else 1,
                                key=f"result_{row_key}"
                            )
                        with col3:
                            st.write(f"**차트번호:** {chart_num}")
                            current_date = row['날짜']
                            st.write(f"**현재 날짜:** {current_date}")
                            st.write("**날짜 수정:**")
                            date_obj = safe_parse_date(current_date) or datetime.now().date()
                            new_date = st.date_input(
                                "변경할 날짜",
                                value=date_obj,
                                key=f"date_{row_key}"
                            )

                        if not unique_id:
                            st.warning("⚠️ 이 기록은 고유ID가 없어 수정할 수 없습니다. 관리자에게 마이그레이션을 요청해주세요.")
                        else:
                            has_changes = (new_result != current_result) or (new_date != date_obj)
                            if has_changes:
                                if st.button("✅ 저장", key=f"save_{row_key}"):
                                    updates = {}
                                    changes = []
                                    if new_result != current_result:
                                        updates["상담결과"] = new_result
                                        changes.append(f"상담결과: {current_result} → {new_result}")
                                    if new_date != date_obj:
                                        updates["날짜"] = new_date.strftime('%Y-%m-%d')
                                        changes.append(f"날짜: {current_date} → {new_date.strftime('%Y-%m-%d')}")

                                    try:
                                        if update_record_fields(ws, unique_id, updates):
                                            load_gsheet_data.clear()
                                            st.success("✅ 변경사항이 저장되었습니다!\n" + "\n".join(changes))
                                            st.rerun()
                                        else:
                                            st.error("❌ 해당 기록을 찾지 못했습니다. 새로고침 후 다시 시도해주세요.")
                                    except Exception:
                                        st.error("❌ 저장 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

                        st.markdown(f"**주요포인트:** {row['주요포인트']}")
                        st.markdown(f"**상담내용:**\n\n{row['상담내용']}")
            else:
                st.warning(f"❌ '{search_patient}'에 해당하는 환자가 없습니다.")
        else:
            st.info("환자 이름 또는 차트번호를 입력해주세요.")
    else:
        st.info("데이터가 없습니다")

# ===== TAB 5: 보고 자료 =====
with tab_summary:
    st.header("📄 상담 보고")

    df_summary_source = load_gsheet_data(ws)

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_counselor_summary = st.selectbox("👤 상담자 선택", ["전체"] + COUNSELORS, key="summary_counselor")
    with col2:
        today = datetime.now().date()
        start_date_summary = st.date_input("시작일", today, key="summary_start")
    with col3:
        end_date_summary = st.date_input("종료일", today, key="summary_end")

    if not df_summary_source.empty:
        df_report = df_summary_source.copy()
        df_report['금액_숫자'] = df_report['금액'].apply(format_amount)

        start_str = start_date_summary.strftime("%Y-%m-%d")
        end_str = end_date_summary.strftime("%Y-%m-%d")
        df_report = df_report[(df_report['날짜'] >= start_str) & (df_report['날짜'] <= end_str)]

        if selected_counselor_summary != "전체":
            df_report = df_report[df_report['상담자'] == selected_counselor_summary]

        if not df_report.empty:
            stats_summary = calculate_stats(df_report)
            st.subheader("📊 상담일지 통계")
            display_stats_metrics(stats_summary)

            st.divider()

            if selected_counselor_summary == "전체":
                st.subheader("👥 상담자별 매출 및 성과")
                counselor_sales_df = get_counselor_stats(df_report, COUNSELORS)
                st.dataframe(counselor_sales_df, use_container_width=True, hide_index=True)
                st.divider()

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

            # ===== ⚠️ 컴플레인 현황 (기간과 무관하게, 현재 조치가 안 된 건만) =====
            st.subheader("⚠️ 컴플레인 현황")
            complaint_ws_summary = get_complaint_worksheet()
            df_complaints_summary = load_complaint_data(complaint_ws_summary)

            if df_complaints_summary.empty:
                st.info("등록된 컴플레인이 없습니다.")
            else:
                unresolved_all = df_complaints_summary[df_complaints_summary['처리상태'] != '완료']
                if unresolved_all.empty:
                    st.success("🎉 조치가 필요한 컴플레인이 없습니다.")
                else:
                    staff_series = unresolved_all['담당자'].replace('', '담당자 미지정')
                    staff_series = staff_series.where(staff_series.notna(), '담당자 미지정')
                    staff_counts = staff_series.value_counts()
                    st.write(f"**🔔 조치가 필요한 컴플레인: 총 {len(unresolved_all)}건**")
                    staff_lines = [f"👤 **{name}**: {cnt}건" for name, cnt in staff_counts.items()]
                    st.warning("\n\n".join(staff_lines))

            st.divider()

            st.metric("📌 상담 건수", f"{len(df_report)}건")

            # ⬇️ CSV 다운로드 (엑셀에서 한글이 깨지지 않도록 utf-8-sig 사용)
            download_cols = ['날짜', '상담자', '진단원장', '환자성함', '차트번호', '분류', '상담결과', '금액', '주요포인트', '상담내용']
            csv_bytes = df_report[download_cols].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "⬇️ 현재 보고 자료 CSV로 다운로드",
                data=csv_bytes,
                file_name=f"상담보고_{start_str}_{end_str}.csv",
                mime="text/csv"
            )

            st.divider()

            df_report_sorted = df_report.sort_values(['날짜', '금액_숫자'], ascending=[True, False])

            st.subheader("📝 상담내용 상세")
            for idx, row in df_report_sorted.iterrows():
                with st.expander(f"📌 {row['날짜']} - {row['환자성함']} (차트: {format_chart_no(row['차트번호'])}) - {row['상담자']}", expanded=True):
                    render_consultation_detail(row, key_prefix=f"summary_{idx}")
        else:
            st.info("해당 기간에 상담 기록이 없습니다")

# ===== TAB 6: 통계 =====
with tab_statistics:
    st.header("📈 통계 분석")

    if "stats_unlocked" not in st.session_state:
        st.session_state.stats_unlocked = False

    if not st.session_state.stats_unlocked:
        st.warning("🔒 이 탭은 비밀번호 입력 후 확인할 수 있습니다.")
        col_pw1, col_pw2, col_pw3 = st.columns([1, 2, 1])
        with col_pw2:
            with st.form("stats_password_form"):
                stats_pw = st.text_input("🔑 비밀번호", type="password", placeholder="비밀번호 입력")
                stats_submit = st.form_submit_button("🔓 확인", use_container_width=True)
                if stats_submit:
                    if stats_pw == STATS_PASSWORD:
                        st.session_state.stats_unlocked = True
                        st.rerun()
                    else:
                        st.error("❌ 비밀번호가 틀렸습니다. 다시 입력해주세요.")
    else:

        df_stats = load_gsheet_data(ws)

        if not df_stats.empty:
            col1, col2, col3 = st.columns(3)
            with col1:
                date_type = st.radio("📅 기간 선택", ["월간", "특정 기간"], horizontal=True, key="stats_date_type")

            if date_type == "월간":
                with col2:
                    selected_year = st.selectbox("연도", range(2020, datetime.now().year + 1), index=datetime.now().year - 2020, key="stats_year")
                with col3:
                    selected_month = st.selectbox("월", range(1, 13), index=datetime.now().month - 1, key="stats_month")
                start_date_stats = datetime(selected_year, selected_month, 1).date()
                last_day = monthrange(selected_year, selected_month)[1]
                end_date_stats = datetime(selected_year, selected_month, last_day).date()
            else:
                with col2:
                    start_date_stats = st.date_input("시작일", datetime.now().date(), key="stats_start")
                with col3:
                    end_date_stats = st.date_input("종료일", datetime.now().date(), key="stats_end")

            df_stats['금액_숫자'] = df_stats['금액'].apply(format_amount)
            df_f = filter_by_date_range(df_stats, start_date_stats, end_date_stats)

            if not df_f.empty:
                st.divider()
                st.subheader("📊 요약 통계")
                total_count = len(df_f)
                total_amount = int(df_f['금액_숫자'].sum())
                confirmed_count = len(df_f[df_f['상담결과'] == '확정'])
                unconfirmed_count = len(df_f[df_f['상담결과'] == '미확정'])
                agreement_rate = (confirmed_count / total_count * 100) if total_count > 0 else 0
                confirmed_amount = int(df_f[df_f['상담결과'] == '확정']['금액_숫자'].sum())
                unconfirmed_amount = int(df_f[df_f['상담결과'] == '미확정']['금액_숫자'].sum())

                c1, c2, c3, c4, c5 = st.columns(5)
                with c1:
                    st.metric("📌 총 상담건수", f"{total_count}건")
                with c2:
                    st.metric("💰 총 매출액", f"{total_amount:,}원")
                with c3:
                    st.metric("✅ 확정건수", f"{confirmed_count}건")
                with c4:
                    st.metric("❌ 미확정건수", f"{unconfirmed_count}건")
                with c5:
                    st.metric("🎯 동의율", f"{agreement_rate:.1f}%")

                ca1, ca2 = st.columns(2)
                with ca1:
                    st.metric("✅ 확정 상담매출 총액", f"{confirmed_amount:,}원")
                with ca2:
                    st.metric("❌ 미확정 상담매출 총액", f"{unconfirmed_amount:,}원")

                st.divider()

                df_confirmed = df_f[df_f['상담결과'] == '확정']
                df_unconfirmed = df_f[df_f['상담결과'] == '미확정']

                st.subheader("👥 상담자별 상담 건수 (확정 / 미확정)")
                col_a, col_b = st.columns(2)

                with col_a:
                    confirmed_cnt = df_confirmed['상담자'].value_counts().sort_values(ascending=False)
                    if not confirmed_cnt.empty:
                        fig = px.bar(
                            x=confirmed_cnt.index, y=confirmed_cnt.values,
                            labels={'x': '상담자', 'y': '확정 건수'},
                            title="상담자별 확정 상담 건수",
                            text_auto=True, color=confirmed_cnt.values,
                            color_continuous_scale="Blues"
                        )
                        fig.update_layout(showlegend=False, height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("확정 상담 데이터가 없습니다")

                with col_b:
                    unconfirmed_cnt = df_unconfirmed['상담자'].value_counts().sort_values(ascending=False)
                    if not unconfirmed_cnt.empty:
                        fig = px.bar(
                            x=unconfirmed_cnt.index, y=unconfirmed_cnt.values,
                            labels={'x': '상담자', 'y': '미확정 건수'},
                            title="상담자별 미확정 상담 건수",
                            text_auto=True, color=unconfirmed_cnt.values,
                            color_continuous_scale="Reds"
                        )
                        fig.update_layout(showlegend=False, height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("미확정 상담 데이터가 없습니다")

                st.divider()

                st.subheader("🎯 상담자별 동의율")
                counselor_total = df_f['상담자'].value_counts()
                counselor_confirmed = df_confirmed['상담자'].value_counts().reindex(counselor_total.index, fill_value=0)
                agree_rate = (counselor_confirmed / counselor_total * 100).sort_values(ascending=False)
                if not agree_rate.empty:
                    agree_df = pd.DataFrame({'상담자': agree_rate.index, '동의율': agree_rate.values})
                    fig_agree = px.bar(
                        agree_df, x='상담자', y='동의율',
                        title="상담자별 동의율 (확정 / 전체)",
                        text='동의율', color='동의율',
                        color_continuous_scale="Tealgrn"
                    )
                    fig_agree.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                    fig_agree.update_layout(showlegend=False, height=400, yaxis_range=[0, 105])
                    st.plotly_chart(fig_agree, use_container_width=True)
                else:
                    st.info("동의율 데이터가 없습니다")

                st.divider()

                st.subheader("💰 상담자별 매출액 (확정 / 미확정)")
                col_c, col_d = st.columns(2)

                with col_c:
                    confirmed_sales = df_confirmed.groupby('상담자')['금액_숫자'].sum().sort_values(ascending=False)
                    if not confirmed_sales.empty:
                        fig = px.bar(
                            x=confirmed_sales.index, y=confirmed_sales.values,
                            labels={'x': '상담자', 'y': '확정 매출액 (원)'},
                            title="상담자별 확정 상담 매출액",
                            text_auto=True, color=confirmed_sales.values,
                            color_continuous_scale="Blues"
                        )
                        fig.update_layout(showlegend=False, height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("확정 매출 데이터가 없습니다")

                with col_d:
                    unconfirmed_sales = df_unconfirmed.groupby('상담자')['금액_숫자'].sum().sort_values(ascending=False)
                    if not unconfirmed_sales.empty:
                        fig = px.bar(
                            x=unconfirmed_sales.index, y=unconfirmed_sales.values,
                            labels={'x': '상담자', 'y': '미확정 매출액 (원)'},
                            title="상담자별 미확정 상담 매출액",
                            text_auto=True, color=unconfirmed_sales.values,
                            color_continuous_scale="Reds"
                        )
                        fig.update_layout(showlegend=False, height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("미확정 매출 데이터가 없습니다")

                st.divider()

                st.subheader("📊 상담자별 확정 / 미확정 매출 비중")
                total_sales = confirmed_sales.add(unconfirmed_sales, fill_value=0).sort_values(ascending=False)
                counselors_with_sales = [c for c in total_sales.index if total_sales[c] > 0]
                if counselors_with_sales:
                    ratio_rows = []
                    for c in counselors_with_sales:
                        conf = int(confirmed_sales.get(c, 0))
                        unconf = int(unconfirmed_sales.get(c, 0))
                        tot = conf + unconf
                        ratio_rows.append({'상담자': c, '구분': '확정', '비중': conf / tot * 100, '매출액': conf})
                        ratio_rows.append({'상담자': c, '구분': '미확정', '비중': unconf / tot * 100, '매출액': unconf})
                    ratio_df = pd.DataFrame(ratio_rows)
                    ratio_df['표시'] = ratio_df['비중'].map(lambda v: f"{v:.1f}%")
                    fig_ratio = px.bar(
                        ratio_df, x='상담자', y='비중', color='구분',
                        title="상담자별 확정/미확정 매출 비중 (100% 기준)",
                        text='표시',
                        color_discrete_map={'확정': '#3366cc', '미확정': '#dc3912'},
                        category_orders={'상담자': counselors_with_sales}
                    )
                    fig_ratio.update_traces(textposition='inside')
                    fig_ratio.update_layout(height=400, yaxis_title='비중 (%)', barmode='stack')
                    st.plotly_chart(fig_ratio, use_container_width=True)
                else:
                    st.info("매출 비중 데이터가 없습니다")

                st.divider()

                st.subheader("✅ 상담 결과 분포")
                result_dist = df_f['상담결과'].value_counts()
                fig_pie = px.pie(
                    values=result_dist.values, names=result_dist.index,
                    title="상담 결과 분포 (확정/미확정)",
                    color=result_dist.index,
                    color_discrete_map={'확정': '#3366cc', '미확정': '#dc3912'},
                    hole=0
                )
                fig_pie.update_layout(height=400)
                st.plotly_chart(fig_pie, use_container_width=True)

                st.divider()

                st.subheader("📈 날짜별 상담 건수 추이")
                daily_count = df_f.groupby('날짜').size().reset_index(name='상담건수').sort_values('날짜')
                fig_daily = px.line(
                    daily_count, x='날짜', y='상담건수',
                    title="날짜별 상담 건수 추이", markers=True, line_shape='linear'
                )
                fig_daily.update_traces(line=dict(color='#3366cc', width=3), marker=dict(size=8))
                fig_daily.update_layout(height=400, hovermode='x unified')
                st.plotly_chart(fig_daily, use_container_width=True)

                st.divider()

                st.subheader("📅 요일별 상담 건수 추이")
                dow = pd.to_datetime(df_f['날짜'], errors='coerce').dt.dayofweek
                dow_count = (
                    dow.dropna().astype(int)
                    .value_counts()
                    .reindex(range(7), fill_value=0)
                    .sort_index()
                )
                weekday_labels = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
                fig_dow = px.line(
                    x=weekday_labels, y=dow_count.values,
                    labels={'x': '요일', 'y': '상담건수'},
                    title="요일별 상담 건수 추이", markers=True, line_shape='linear'
                )
                fig_dow.update_traces(line=dict(color='#2ca02c', width=3), marker=dict(size=8))
                fig_dow.update_layout(height=400, hovermode='x unified')
                st.plotly_chart(fig_dow, use_container_width=True)
            else:
                st.info("해당 기간에 상담 기록이 없습니다")
        else:
            st.info("데이터가 없습니다")

