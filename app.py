import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import io
import json
import os
import FinanceDataReader as fdr
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

# --- 0. 한글 폰트 자동 설정 (차트 한글 깨짐 방지) ---
@st.cache_resource
def init_korean_font():
    """Matplotlib 한글 폰트 깨짐(가가가가) 자동 방지 설정"""
    try:
        font_list = [f.name for f in fm.fontManager.ttflist]
        if "NanumGothic" in font_list:
            plt.rcParams['font.family'] = 'NanumGothic'
        elif "Malgun Gothic" in font_list:
            plt.rcParams['font.family'] = 'Malgun Gothic'
        elif "AppleGothic" in font_list:
            plt.rcParams['font.family'] = 'AppleGothic'
        else:
            os.system('apt-get -y install fonts-nanum')
            fm.fontManager.addfont('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
            plt.rcParams['font.family'] = 'NanumGothic'
    except Exception:
        plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['axes.unicode_minus'] = False

init_korean_font()

# --- 1. 페이지 설정 및 디자인 세팅 ---
st.set_page_config(
    page_title="개인 트레이딩 분석 & 일지 툴", page_icon="📈", layout="wide"
)

st.title("📈 개인 주도주 분석 & 매매 일지 시스템")
st.markdown(
    "지수 바닥일 대비 강력한 주도주를 발굴하고, 차트와 함께 매매 복기를 기록하는 나만의 프라이빗 툴입니다."
)

NOTE_FILE = "trade_notes.json"


# --- 2. 데이터 수집 및 백엔드 로직 ---
@st.cache_data(ttl=3600)
def get_market_data(symbol, start_date, end_date=None):
    """지수 및 종목 데이터를 불러오는 함수"""
    try:
        df = fdr.DataReader(symbol, start_date, end_date)
        if df is None or df.empty:
            return None
        return df
    except Exception:
        return None


def load_notes():
    if os.path.exists(NOTE_FILE):
        try:
            with open(NOTE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_notes(notes):
    with open(NOTE_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=4)


# 개별 종목 수집 및 계산 워커 함수 (멀티스레딩용)
def process_single_stock(row, target_market, benchmark_code, df_single_bench, search_start_date, analysis_date_str, filters):
    code = row["Code"]
    name = row["Name"]
    mkt = row.get("Market", target_market)
    marcap = row.get("Marcap", 0)

    # 지수 선택
    if benchmark_code == "AUTO":
        curr_b_code = "KQ11" if mkt == "KOSDAQ" else "KS11"
        df_bench = get_market_data(curr_b_code, search_start_date, analysis_date_str)
    else:
        df_bench = df_single_bench

    df_stock = get_market_data(code, search_start_date, analysis_date_str)

    if df_bench is None or df_bench.empty or df_stock is None or df_stock.empty:
        return None

    common_dates = df_bench.index.intersection(df_stock.index)
    df_b_filtered = df_bench.loc[common_dates]
    df_s_filtered = df_stock.loc[common_dates]

    if len(df_b_filtered) < 2 or len(df_s_filtered) < 2:
        return None

    # 지수 최저점(바닥일) 탐색
    trough_date = df_b_filtered["Close"].idxmin()
    base_bench_price = df_b_filtered.loc[trough_date, "Close"]
    curr_bench_price = df_b_filtered["Close"].iloc[-1]

    s_base = df_s_filtered.loc[trough_date, "Close"]
    s_curr = df_s_filtered["Close"].iloc[-1]

    if base_bench_price <= 0 or s_base <= 0:
        return None

    bench_growth = ((curr_bench_price / base_bench_price) - 1.0) * 100.0
    stock_growth = ((s_curr / s_base) - 1.0) * 100.0

    stock_factor = s_curr / s_base
    bench_factor = curr_bench_price / base_bench_price
    rel_strength = ((stock_factor / bench_factor) - 1.0) * 100.0

    trading_val = s_curr * df_s_filtered["Volume"].iloc[-1]
    max_vol = df_s_filtered["Volume"].max()
    curr_vol = df_s_filtered["Volume"].iloc[-1]
    vol_ratio = (curr_vol / max_vol * 100.0) if max_vol > 0 else 0.0

    marcap_eok = marcap / 1e8 if marcap else 0
    trading_val_eok = trading_val / 1e8

    # 필터 체크
    if filters["mc_min"] > 0 and marcap_eok < filters["mc_min"]:
        return None
    if filters["mc_max"] > 0 and marcap_eok > filters["mc_max"]:
        return None
    if filters["price_min"] > 0 and s_curr < filters["price_min"]:
        return None
    if filters["price_max"] > 0 and s_curr > filters["price_max"]:
        return None
    if filters["val_min"] > 0 and trading_val_eok < filters["val_min"]:
        return None
    if filters["val_max"] > 0 and trading_val_eok > filters["val_max"]:
        return None
    if filters["rs_min"] != 0.0 and rel_strength < filters["rs_min"]:
        return None
    if filters["rs_max"] != 0.0 and rel_strength > filters["rs_max"]:
        return None
    if filters["vol_ratio_min"] != 0.0 and vol_ratio < filters["vol_ratio_min"]:
        return None
    if filters["vol_ratio_max"] != 0.0 and vol_ratio > filters["vol_ratio_max"]:
        return None

    return {
        "시장": mkt,
        "종목명": name,
        "시가총액(억)": f"{marcap_eok:,.0f}" if marcap_eok > 0 else "-",
        "현재가(원)": f"{s_curr:,.0f}",
        "거래대금(억)": f"{trading_val_eok:,.0f}",
        "종목수익률(%)": round(stock_growth, 2),
        "거래량 비율(%)": f"{vol_ratio:.1f}%",
        "상대강도(%)": round(rel_strength, 2),
        "지수바닥일": trough_date.strftime("%Y-%m-%d"),
        "_code": code,
    }


# --- 3. 사이드바 (상세 필터 설정) ---
st.sidebar.header("🛠️ 상세 필터")

top_n = st.sidebar.number_input(
    "상위 N개 분석 제한 (시총 기준)", min_value=0, value=300, step=50
)
if top_n > 0:
    st.sidebar.caption(f"💡 설정값: 시총 상위 {top_n:,}개 종목만 분석")
else:
    st.sidebar.caption("💡 설정값: 전체 종목 대상 분석 (제한 없음)")

st.sidebar.markdown("---")

st.sidebar.subheader("시가총액 (억 원)")
mc_col1, mc_col2 = st.sidebar.columns(2)
with mc_col1:
    mc_min = st.number_input("최소", min_value=0, value=0, step=100, key="mc_min")
with mc_col2:
    mc_max = st.number_input("최대", min_value=0, value=0, step=100, key="mc_max")
if mc_min > 0 or mc_max > 0:
    st.sidebar.caption(f"💡 범위: {mc_min:,}억 원 ~ {mc_max:, if mc_max > 0 else '제한없음'}억 원")

st.sidebar.subheader("현재가 (원)")
p_col1, p_col2 = st.sidebar.columns(2)
with p_col1:
    price_min = st.number_input("최소", min_value=0, value=0, step=500, key="p_min")
with p_col2:
    price_max = st.number_input("최대", min_value=0, value=0, step=1000, key="p_max")
if price_min > 0 or price_max > 0:
    st.sidebar.caption(f"💡 범위: {price_min:,}원 ~ {price_max:, if price_max > 0 else '제한없음'}원")

st.sidebar.subheader("당일 거래대금 (억 원)")
val_col1, val_col2 = st.sidebar.columns(2)
with val_col1:
    val_min = st.number_input("최소", min_value=0, value=0, step=10, key="v_min")
with val_col2:
    val_max = st.number_input("최대", min_value=0, value=0, step=10, key="v_max")
if val_min > 0 or val_max > 0:
    st.sidebar.caption(f"💡 범위: {val_min:,}억 원 ~ {val_max:, if val_max > 0 else '제한없음'}억 원")

st.sidebar.subheader("상대강도 RS (%)")
rs_col1, rs_col2 = st.sidebar.columns(2)
with rs_col1:
    rs_min = st.number_input("최소", value=0.0, step=1.0, key="rs_min")
with rs_col2:
    rs_max = st.number_input("최대", value=0.0, step=1.0, key="rs_max")

st.sidebar.subheader("거래량 비율 (%)")
st.sidebar.caption("ℹ️ 조회 기간 내 최고 거래량 대비 분석일 당일 거래량의 비율입니다.")
vr_col1, vr_col2 = st.sidebar.columns(2)
with vr_col1:
    vol_ratio_min = st.number_input("최소", value=0.0, step=5.0, key="vr_min")
with vr_col2:
    vol_ratio_max = st.number_input("최대", value=0.0, step=5.0, key="vr_max")


# --- 4. 메인 탭 구성 ---
tab1, tab2, tab3 = st.tabs(
    ["📊 상대강도 분석", "🔍 종목 상세 및 추이 차트", "📝 매매 복기 일지"]
)

# -------------------------------------------------------------------------
# [탭 1] 상대강도 분석
# -------------------------------------------------------------------------
with tab1:
    st.subheader("1. 시장 대비 상대강도 분석")

    st.markdown("##### 📅 1구역: 날짜 및 기간 설정")
    d_col1, d_col2, d_col3 = st.columns(3)

    with d_col1:
        analysis_date = st.date_input(
            "분석일 (기본값: 오늘)", value=datetime.today(), help="분석의 종료 기준 날짜입니다."
        )

    with d_col2:
        period_num = st.number_input(
            "기간 숫자", min_value=1, max_value=365, value=4, help="분석일 기준 과거 탐색할 기간 숫자를 입력합니다."
        )

    with d_col3:
        period_unit = st.selectbox(
            "기간 단위", ["일 전", "주 전", "개월 전"]
        )

    st.markdown("##### 🎯 2구역: 대상 시장 및 지수 설정")
    m_col1, m_col2 = st.columns(2)

    with m_col1:
        index_options = {
            "[자동] 종목별 시장 지수 매칭 (KOSPI↔KS11, KOSDAQ↔KQ11)": "AUTO",
            "코스피 (KS11)": "KS11",
            "코스닥 (KQ11)": "KQ11",
            "코스피 200 (KS200)": "KS200",
            "KODEX 200 (069500)": "069500",
            "코스닥 150 (229200)": "229200",
        }
        selected_idx_name = st.selectbox(
            "기준 지수/ETF 선택", list(index_options.keys())
        )
        benchmark_code = index_options[selected_idx_name]

    with m_col2:
        market_type = st.selectbox(
            "대상 시장", ["KRX (전체)", "KOSPI", "KOSDAQ"]
        )

    analysis_date_str = analysis_date.strftime("%Y-%m-%d")
    if "일 전" in period_unit:
        delta_days = period_num
    elif "주 전" in period_unit:
        delta_days = period_num * 7
    else:
        delta_days = period_num * 30

    search_start_date = (analysis_date - timedelta(days=delta_days)).strftime("%Y-%m-%d")

    st.markdown("---")

    if st.button("🚀 분석 실행", type="primary"):
        with st.spinner("⚡ 초고속 멀티스레딩 엔진으로 전 종목을 실시간 분석 중입니다..."):
            target_market = "KRX" if "전체" in market_type else market_type
            df_krx = fdr.StockListing(target_market)

            if top_n > 0:
                df_krx = df_krx.head(top_n)

            st.session_state["benchmark_code"] = benchmark_code
            st.session_state["selected_idx_name"] = selected_idx_name
            st.session_state["analysis_date_str"] = analysis_date_str
            st.session_state["search_start_date"] = search_start_date

            df_single_bench = None
            if benchmark_code != "AUTO":
                df_single_bench = get_market_data(benchmark_code, search_start_date, analysis_date_str)

            filters = {
                "mc_min": mc_min, "mc_max": mc_max,
                "price_min": price_min, "price_max": price_max,
                "val_min": val_min, "val_max": val_max,
                "rs_min": rs_min, "rs_max": rs_max,
                "vol_ratio_min": vol_ratio_min, "vol_ratio_max": vol_ratio_max
            }

            results = []
            rows = [row for _, row in df_krx.iterrows()]

            # ⚡ 16개 동시 실행 병렬 연산 처리
            with ThreadPoolExecutor(max_workers=16) as executor:
                futures = [
                    executor.submit(
                        process_single_stock,
                        row, target_market, benchmark_code, df_single_bench,
                        search_start_date, analysis_date_str, filters
                    )
                    for row in rows
                ]

                progress_bar = st.progress(0)
                total_items = len(futures)

                for idx, future in enumerate(as_completed(futures)):
                    res = future.result()
                    if res is not None:
                        results.append(res)
                    progress_bar.progress((idx + 1) / total_items)

            if results:
                df_result = pd.DataFrame(results)
                # 상대강도 기준 내림차순 정렬
                df_result = df_result.sort_values(by="상대강도(%)", ascending=False).reset_index(drop=True)
                st.session_state["analysis_result"] = df_result
                st.success(f"분석 완료! 조건에 맞는 총 {len(df_result)}개 종목이 검색되었습니다.")
            else:
                st.warning("조건에 맞는 종목 데이터를 찾지 못했습니다.")

    if "analysis_result" in st.session_state:
        df_res = st.session_state["analysis_result"]
        st.subheader("📋 분석 결과 목록")
        st.caption("ℹ️ 거래량 비율(%) = 기간 내 최고 거래량 대비 분석일 당일 거래량 비율")
        display_cols = [col for col in df_res.columns if col != "_code"]
        st.dataframe(df_res[display_cols], use_container_width=True)


# -------------------------------------------------------------------------
# [탭 2] 종목 상세 및 추이 차트
# -------------------------------------------------------------------------
with tab2:
    st.subheader("2. 종목별 상세 추이 분석 (2단 비교 차트)")

    if "analysis_result" in st.session_state:
        df_target = st.session_state["analysis_result"]
        
        c1, c2 = st.columns([2, 1])
        with c1:
            selected_name = st.selectbox("분석할 종목 선택", df_target["종목명"].tolist())
        with c2:
            chart_bench_option = st.selectbox(
                "비교 기준 지수 변경",
                ["[자동] 종목 시장에 매칭", "코스피 (KS11)", "코스닥 (KQ11)", "KODEX 200 (069500)"],
            )

        if selected_name:
            target_row = df_target[df_target["종목명"] == selected_name].iloc[0]
            t_code = target_row["_code"]
            t_mkt = target_row["시장"]
            trough_d_str = target_row["지수바닥일"]

            st.write(
                f"**선택 종목:** {selected_name} ({t_code}) | **현재가:** {target_row['현재가(원)']}원 | **지수 바닥일:** {trough_d_str} | **상대강도:** {target_row['상대강도(%)']}%"
            )

            if st.button("📊 상세 추이 차트 그리기", type="primary"):
                with st.spinner("차트 데이터를 계산 중입니다..."):
                    s_date_str = st.session_state.get("search_start_date", search_start_date)
                    e_date_str = st.session_state.get("analysis_date_str", analysis_date_str)

                    if "자동" in chart_bench_option:
                        ch_b_code = "KQ11" if t_mkt == "KOSDAQ" else "KS11"
                        ch_b_name = "코스닥" if t_mkt == "KOSDAQ" else "코스피"
                    elif "KS11" in chart_bench_option:
                        ch_b_code, ch_b_name = "KS11", "코스피"
                    elif "KQ11" in chart_bench_option:
                        ch_b_code, ch_b_name = "KQ11", "코스닥"
                    else:
                        ch_b_code, ch_b_name = "069500", "KODEX 200"

                    df_s = get_market_data(t_code, s_date_str, e_date_str)
                    df_b = get_market_data(ch_b_code, s_date_str, e_date_str)

                    if df_s is not None and df_b is not None:
                        common_idx = df_s.index.intersection(df_b.index)
                        df_s = df_s.loc[common_idx]
                        df_b = df_b.loc[common_idx]

                        if not df_s.empty and pd.Timestamp(trough_d_str) in common_idx:
                            s_trough_price = df_s.loc[trough_d_str, "Close"]
                            b_trough_price = df_b.loc[trough_d_str, "Close"]

                            stock_cum_ret = (df_s["Close"] / s_trough_price - 1.0) * 100
                            bench_cum_ret = (df_b["Close"] / b_trough_price - 1.0) * 100

                            stock_factor = df_s["Close"] / s_trough_price
                            bench_factor = df_b["Close"] / b_trough_price
                            rs_trend = ((stock_factor / bench_factor) - 1.0) * 100

                            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

                            ax1.plot(common_idx, stock_cum_ret, label=f"{selected_name} (종목)", color="crimson", linewidth=2)
                            ax1.plot(common_idx, bench_cum_ret, label=f"{ch_b_name} (지수)", color="dodgerblue", linewidth=2, linestyle="--")
                            ax1.axvline(pd.Timestamp(trough_d_str), color="purple", linestyle=":", alpha=0.8, label=f"지수 바닥일 ({trough_d_str})")
                            ax1.set_title(f"[{selected_name}] 지수 바닥일 기준 누적 수익률 비교 (%)")
                            ax1.set_ylabel("수익률 (%)")
                            ax1.legend()
                            ax1.grid(True, alpha=0.3)

                            ax2.plot(common_idx, rs_trend, label="상대강도 추이 (초과 성과 %)", color="forestgreen", linewidth=2)
                            ax2.axhline(0, color="gray", linestyle=":", alpha=0.7)
                            ax2.axvline(pd.Timestamp(trough_d_str), color="purple", linestyle=":", alpha=0.8)
                            ax2.set_title("상대강도 비율 추이 (우상향 = 주도력 강화)")
                            ax2.set_ylabel("상대강도 (%)")
                            ax2.set_xlabel("날짜")
                            ax2.legend()
                            ax2.grid(True, alpha=0.3)

                            plt.tight_layout()
                            st.pyplot(fig)
                        else:
                            st.error("지수 바닥일 시점의 데이터를 불러오지 못했습니다.")
    else:
        st.info("먼저 [탭 1]에서 '분석 실행'을 진행하여 종목 리스트를 생성해 주세요.")


# -------------------------------------------------------------------------
# [탭 3] 매매 복기 및 차트 게시판 (일지 & 백업)
# -------------------------------------------------------------------------
with tab3:
    st.subheader("3. 나만의 매매 일지 및 차트 복기 게시판")

    notes = load_notes()

    with st.form("note_form", clear_on_submit=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            note_date = st.date_input("작성일자", value=datetime.today())
        with f_col2:
            note_title = st.text_input("종목명 또는 제목", placeholder="예: 삼성전자 매매 복기")
        with f_col3:
            note_category = st.selectbox(
                "카테고리", ["매매복기", "관심종목 아이디어", "시장트렌드 메모", "기타"]
            )

        note_content = st.text_area(
            "상세 내용 (진입 근거, 심리, 배운 점 등)", placeholder="자세한 일기를 적어보세요..."
        )
        uploaded_image = st.file_uploader(
            "차트 캡처 이미지 첨부 (PNG, JPG)", type=["png", "jpg", "jpeg"]
        )

        submitted = st.form_submit_button("📝 일지 저장하기")

        if submitted:
            if not note_title.strip():
                st.warning("종목명 또는 제목을 입력해주세요.")
            else:
                img_base64 = ""
                if uploaded_image is not None:
                    bytes_data = uploaded_image.getvalue()
                    img_base64 = base64.b64encode(bytes_data).decode("utf-8")

                new_note = {
                    "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "date": str(note_date),
                    "title": note_title,
                    "category": note_category,
                    "content": note_content,
                    "image": img_base64,
                }
                notes.insert(0, new_note)
                save_notes(notes)
                st.success("매매 일지가 안전하게 저장되었습니다!")
                st.rerun()

    st.markdown("---")
    st.subheader("📁 저장된 일지 목록 보기")

    if not notes:
        st.info("아직 작성된 매매 일지가 없습니다. 위 폼을 채워 첫 일지를 작성해 보세요!")
    else:
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            json_str = json.dumps(notes, ensure_ascii=False, indent=4)
            st.download_button(
                label="📥 내 모든 일지 백업 파일(JSON) 다운로드",
                data=json_str,
                file_name=f"trade_notes_backup_{datetime.today().strftime('%Y%m%d')}.json",
                mime="application/json",
            )
        with b_col2:
            uploaded_backup = st.file_uploader(
                "📤 백업 파일 업로드하여 복구하기", type=["json"]
            )
            if uploaded_backup is not None:
                try:
                    restored_notes = json.load(uploaded_backup)
                    save_notes(restored_notes)
                    st.success("백업 파일이 성공적으로 복구되었습니다!")
                    st.rerun()
                except Exception as e:
                    st.error(f"복구 중 오류가 발생했습니다: {e}")

        st.markdown("### 📋 일지 리스트")
        for i, note in enumerate(notes):
            with st.expander(f"[{note['category']}] {note['date']} - {note['title']}"):
                st.write(f"**작성일:** {note['date']}")
                st.write(f"**내용:**\n\n{note['content']}")

                if note.get("image"):
                    try:
                        img_bytes = base64.b64decode(note["image"])
                        st.image(img_bytes, caption="첨부된 차트 캡처", use_column_width=True)
                    except Exception:
                        st.warning("이미지를 불러오는 중 오류가 발생했습니다.")

                if st.button("🗑️ 이 일지 삭제하기", key=f"del_{note['id']}"):
                    notes.pop(i)
                    save_notes(notes)
                    st.success("일지가 삭제되었습니다.")
                    st.rerun()
