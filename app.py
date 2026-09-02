import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os
import platform
import json
import base64
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# ---------------------------------------------------------
# 0. 한글 폰트 및 UI 스타일 설정
# ---------------------------------------------------------
@st.cache_resource
def init_korean_font():
    system_name = platform.system()
    if system_name == "Linux":
        os.system("apt-get update -qq && apt-get install -y -qq fonts-nanum")
        font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        if os.path.exists(font_path):
            fm.fontManager.addfont(font_path)
            plt.rc("font", family="NanumGothic")
        else:
            plt.rc("font", family="DejaVu Sans")
    elif system_name == "Windows":
        plt.rc("font", family="Malgun Gothic")
    elif system_name == "Darwin":
        plt.rc("font", family="AppleGothic")
    plt.rcParams["axes.unicode_minus"] = False

init_korean_font()

st.set_page_config(page_title="주도주 & 매매일지 분석기", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    .stButton>button { width: 100%; border-radius: 6px; font-weight: bold; }
</style>
""", unsafe_allow_cookies=True)

# ---------------------------------------------------------
# 1. 데이터 수집 및 멀티스레딩 데이터 처리 연산 엔진
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_krx_listing():
    return fdr.StockListing('KRX')

@st.cache_data(ttl=3600)
def get_market_data(ticker, start_date, end_date):
    try:
        df = fdr.DataReader(ticker, start_date, end_date)
        return df if not df.empty else None
    except Exception:
        return None

def process_single_stock(row, end_date_str, lookback_days, vol_lookback_days, min_mc, max_mc, min_pr, max_pr, min_amt, max_amt, min_rs, max_rs, min_vol_r, max_vol_r, custom_trough_date, df_bench):
    ticker = str(row['Code'])
    name = str(row['Name'])
    market = str(row.get('Market', ''))

    # 시작일 계산
    try:
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        return None
        
    start_dt = end_dt - timedelta(days=int(lookback_days * 1.5))
    start_date_str = start_dt.strftime("%Y-%m-%d")

    df_stock = get_market_data(ticker, start_date_str, end_date_str)
    if df_stock is None or len(df_stock) < 10:
        return None

    # 분석일 기준 데이터 매칭
    df_s_filtered = df_stock[df_stock.index <= end_date_str]
    df_b_filtered = df_bench[df_bench.index <= end_date_str]

    if df_s_filtered.empty or df_b_filtered.empty:
        return None

    # 공통 날짜 인덱스 확보
    common_idx = df_s_filtered.index.intersection(df_b_filtered.index)
    if len(common_idx) < 10:
        return None

    df_s_filtered = df_s_filtered.loc[common_idx]
    df_b_filtered = df_b_filtered.loc[common_idx]

    # 바닥일 지정 (수동 지정 날짜 유효성 검증 후 적용, 없으면 지수 최저점 자동 탐색)
    if custom_trough_date and custom_trough_date in df_b_filtered.index:
        trough_date = custom_trough_date
    else:
        trough_date = df_b_filtered["Close"].idxmin()

    # 바닥일 이후 데이터 슬라이싱
    df_s_post = df_s_filtered.loc[trough_date:]
    df_b_post = df_b_filtered.loc[trough_date:]

    if len(df_s_post) < 1:
        return None

    # 수익률 및 상대강도(RS) 계산
    stock_return = (df_s_post["Close"].iloc[-1] / df_s_post["Close"].iloc[0] - 1) * 100
    bench_return = (df_b_post["Close"].iloc[-1] / df_b_post["Close"].iloc[0] - 1) * 100
    rs_score = stock_return - bench_return

    # 분석일 기준 주가, 상장주식수, 시가총액, 거래대금 동기화
    curr_price = float(df_s_filtered["Close"].iloc[-1])
    curr_vol = float(df_s_filtered["Volume"].iloc[-1])

    # 상장주식수 기반 분석일 시가총액 추정 (없을 경우 상장 정보 기본값 활용)
    shares = row.get('ListingShares', None)
    if shares and not np.isnan(shares) and shares > 0:
        calc_market_cap = (curr_price * shares) / 1e8  # 억원 단위
    else:
        calc_market_cap = float(row.get('Marcap', 0)) / 1e8

    # 분석일 당일 거래대금 계산 (억원)
    curr_amount = (curr_price * curr_vol) / 1e8

    # 최근 N일(vol_lookback_days) 내 최고 거래량 대비 당일 거래량 비율 계산 (거래량 수축률)
    vol_window = df_s_filtered["Volume"].tail(vol_lookback_days)
    max_vol = vol_window.max() if not vol_window.empty else 0
    vol_ratio = (curr_vol / max_vol * 100) if max_vol > 0 else 0.0

    # 조건 필터링
    if not (min_mc <= calc_market_cap <= max_mc): return None
    if not (min_pr <= curr_price <= max_pr): return None
    if not (min_amt <= curr_amount <= max_amt): return None
    if not (min_rs <= rs_score <= max_rs): return None
    if not (min_vol_r <= vol_ratio <= max_vol_r): return None

    return {
        "종목코드": ticker,
        "종목명": name,
        "시장": market,
        "현재가": int(curr_price),
        "시가총액(억)": round(calc_market_cap, 1),
        "거래대금(억)": round(curr_amount, 1),
        "지수바닥일": trough_date.strftime("%Y-%m-%d"),
        "종목수익률(%)": round(stock_return, 2),
        "지수수익률(%)": round(bench_return, 2),
        "상대강도(RS)": round(rs_score, 2),
        f"거래량비율({vol_lookback_days}일Max대비%)": round(vol_ratio, 1)
    }

# ---------------------------------------------------------
# 2. 사이드바 - 파라미터 및 필터 설정
# ---------------------------------------------------------
st.sidebar.header("🔍 주도주 검색 필터")

mc_min, mc_max = st.sidebar.slider("시가총액 범위 (억원)", 0, 100000, (300, 50000), step=100)
pr_min, pr_max = st.sidebar.slider("현재가 범위 (원)", 0, 500000, (1000, 200000), step=500)
amt_min, amt_max = st.sidebar.slider("당일 거래대금 범위 (억원)", 0, 10000, (50, 5000), step=10)
rs_min, rs_max = st.sidebar.slider("상대강도(RS) 범위", -100, 300, (10, 200), step=5)

st.sidebar.subheader("📉 거래량 수축(조정) 설정")
vol_lookback = st.sidebar.number_input("거래량 비교 기간 (최근 N일)", min_value=5, max_value=120, value=20)
vol_r_min, vol_r_max = st.sidebar.slider(f"최근 {vol_lookback}일 최고 거래량 대비 비율 (%)", 0, 100, (0, 80))

st.sidebar.caption(f"💡 현재 설정: 시총 {mc_min}~{mc_max}억 | 거래대금 {amt_min}~{amt_max}억 | 최근 {vol_lookback}일 최고 거래량의 {vol_r_min}~{vol_r_max}% 수준 거래량 종목 검색")

# ---------------------------------------------------------
# 3. 메인 화면 및 탭 구성
# ---------------------------------------------------------
st.title("📈 주식 주도주(RS) 분석 & 매매일지 모니터")

tab1, tab2, tab3 = st.tabs(["🚀 상대강도(RS) 분석", "📊 종목 상세 추이 차트", "📝 매매 복기일지"])

# ---------------------------------------------------------
# TAB 1: RS 분석
# ---------------------------------------------------------
with tab1:
    st.markdown("### 🎯 시장 지수 대비 주도주 선별")
    
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        target_date = st.date_input("분석 기준일", datetime.today())
    with col2:
        lookback_period = st.selectbox("탐색 범위 (일)", [60, 120, 252, 500], index=2)
    with col3:
        bench_code = st.selectbox("비교 기준 지수", ["KS11", "KQ11"], format_func=lambda x: "코스피 (KS11)" if x == "KS11" else "코스닥 (KQ11)")
    with col4:
        st.write("")
        st.write("")
        run_analysis = st.button("🚀 분석 실행", use_container_width=True)

    target_date_str = target_date.strftime("%Y-%m-%d")

    # 분석 실행 처리
    if run_analysis:
        with st.spinner("데이터 수집 및 주도주 탐색 중... (안정화 멀티스레드 구동)"):
            # 공통 지수 데이터 사전 수집 (반복 수집 방지)
            start_dt = target_date - timedelta(days=int(lookback_period * 1.5))
            df_bench_common = get_market_data(bench_code, start_dt.strftime("%Y-%m-%d"), target_date_str)

            if df_bench_common is None or df_bench_common.empty:
                st.error("지수 데이터를 가져올 수 없습니다. 날짜 설정을 확인해주세요.")
            else:
                df_krx = get_krx_listing()
                results = []

                # 지수 바닥일 사전 파악 (기본 자동 탐색용)
                df_bench_sub = df_bench_common[df_bench_common.index <= target_date_str]
                auto_trough = df_bench_sub["Close"].idxmin() if not df_bench_sub.empty else None

                # 스레드 수 6개로 안정화 조정
                with ThreadPoolExecutor(max_workers=6) as executor:
                    futures = [
                        executor.submit(
                            process_single_stock,
                            row, target_date_str, lookback_period, vol_lookback,
                            mc_min, mc_max, pr_min, pr_max, amt_min, amt_max,
                            rs_min, rs_max, vol_r_min, vol_r_max, None, df_bench_common
                        )
                        for _, row in df_krx.iterrows()
                    ]
                    for future in futures:
                        res = future.result()
                        if res:
                            results.append(res)

                if results:
                    df_res = pd.DataFrame(results).sort_values(by="상대강도(RS)", ascending=False)
                    st.session_state["analysis_results"] = df_res
                    st.session_state["auto_trough_date"] = auto_trough.strftime("%Y-%m-%d") if auto_trough else target_date_str
                    st.session_state["bench_code"] = bench_code
                    st.session_state["target_date_str"] = target_date_str
                    st.session_state["lookback_period"] = lookback_period
                    st.success(f"총 {len(df_res)}개 주도주 종목이 선별되었습니다!")
                else:
                    st.warning("조건에 부합하는 종목이 없습니다. 사이드바 필터 조건을 조절해보세요.")

    # 결과 출력 및 지수 바닥일 수동 재지정 기능
    if "analysis_results" in st.session_state and not st.session_state["analysis_results"].empty:
        st.markdown("---")
        st.markdown("#### 📅 지수 바닥일 기준 변경 (필요 시 수동 재지정)")
        
        c_date1, c_date2 = st.columns([3, 5])
        with c_date1:
            default_trough_dt = datetime.strptime(st.session_state.get("auto_trough_date", target_date_str), "%Y-%m-%d")
            custom_trough = st.date_input("바닥일 직접 지정", default_trough_dt)
            custom_trough_str = custom_trough.strftime("%Y-%m-%d")
        
        with c_date2:
            st.write("")
            st.write("")
            if st.button("🔄 선택한 바닥일 기준으로 상대강도 즉시 재계산"):
                with st.spinner("변경한 바닥일 기준으로 즉시 재계산 중..."):
                    bench_c = st.session_state["bench_code"]
                    t_date_s = st.session_state["target_date_str"]
                    lb_p = st.session_state["lookback_period"]
                    
                    s_dt = datetime.strptime(t_date_s, "%Y-%m-%d") - timedelta(days=int(lb_p * 1.5))
                    df_bench_c = get_market_data(bench_c, s_dt.strftime("%Y-%m-%d"), t_date_s)
                    
                    df_krx = get_krx_listing()
                    new_results = []
                    
                    with ThreadPoolExecutor(max_workers=6) as executor:
                        futures = [
                            executor.submit(
                                process_single_stock,
                                row, t_date_s, lb_p, vol_lookback,
                                mc_min, mc_max, pr_min, pr_max, amt_min, amt_max,
                                rs_min, rs_max, vol_r_min, vol_r_max, custom_trough_str, df_bench_c
                            )
                            for _, row in df_krx.iterrows()
                        ]
                        for future in futures:
                            res = future.result()
                            if res:
                                new_results.append(res)
                    
                    if new_results:
                        df_res_new = pd.DataFrame(new_results).sort_values(by="상대강도(RS)", ascending=False)
                        st.session_state["analysis_results"] = df_res_new
                        st.success(f"기준 바닥일({custom_trough_str}) 반영 완료!")
                        st.rerun()

        st.dataframe(st.session_state["analysis_results"], use_container_width=True)

# ---------------------------------------------------------
# TAB 2: 종목 상세 및 추이 차트
# ---------------------------------------------------------
with tab2:
    st.markdown("### 📊 종목 vs 지수 누적 수익률 및 RS 추이 비교")
    
    if "analysis_results" in st.session_state and not st.session_state["analysis_results"].empty:
        df_res = st.session_state["analysis_results"]
        stock_list = [f"{row['종목명']} ({row['종목코드']})" for _, row in df_res.iterrows()]
        
        col_sel1, col_sel2 = st.columns([3, 3])
        with col_sel1:
            selected_stock_str = st.selectbox("분석할 종목 선택", stock_list)
            selected_code = selected_stock_str.split("(")[1].replace(")", "").strip()
            selected_name = selected_stock_str.split("(")[0].strip()
        with col_sel2:
            chart_bench_code = st.selectbox("차트 비교 지수", ["KS11", "KQ11"], index=0 if st.session_state.get("bench_code")=="KS11" else 1)

        t_date_str = st.session_state.get("target_date_str", datetime.today().strftime("%Y-%m-%d"))
        lb_p = st.session_state.get("lookback_period", 252)
        s_dt = datetime.strptime(t_date_str, "%Y-%m-%d") - timedelta(days=int(lb_p * 1.5))

        df_s = get_market_data(selected_code, s_dt.strftime("%Y-%m-%d"), t_date_str)
        df_b = get_market_data(chart_bench_code, s_dt.strftime("%Y-%m-%d"), t_date_str)

        if df_s is not None and df_b is not None:
            common_idx = df_s.index.intersection(df_b.index)
            df_s = df_s.loc[common_idx]
            df_b = df_b.loc[common_idx]

            # 바닥일 실시간 동적 재계산
            trough_date_dt = df_b["Close"].idxmin()
            
            df_s_post = df_s.loc[trough_date_dt:]
            df_b_post = df_b.loc[trough_date_dt:]

            # 누적 수익률(%)
            s_cum = (df_s_post["Close"] / df_s_post["Close"].iloc[0] - 1) * 100
            b_cum = (df_b_post["Close"] / df_b_post["Close"].iloc[0] - 1) * 100
            rs_trend = s_cum - b_cum

            # 차트 시각화 (2단 차트)
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})

            ax1.plot(s_cum.index, s_cum, label=f"{selected_name} 누적수익률(%)", color="red", linewidth=2)
            ax1.plot(b_cum.index, b_cum, label=f"지수({chart_bench_code}) 누적수익률(%)", color="gray", linestyle="--")
            ax1.axvline(trough_date_dt, color="blue", linestyle=":", label=f"지수 바닥일 ({trough_date_dt.strftime('%Y-%m-%d')})")
            ax1.set_title(f"[{selected_name}] 지수 바닥일 이후 누적 수익률 비교", fontsize=14, fontweight="bold")
            ax1.set_ylabel("수익률 (%)")
            ax1.legend(loc="upper left")
            ax1.grid(True, alpha=0.3)

            ax2.plot(rs_trend.index, rs_trend, label="상대강도(RS) 추이", color="green", linewidth=1.8)
            ax2.axhline(0, color="black", linestyle="-", alpha=0.5)
            ax2.axvline(trough_date_dt, color="blue", linestyle=":")
            ax2.set_ylabel("RS 점수")
            ax2.set_xlabel("날짜")
            ax2.legend(loc="upper left")
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()
            st.pyplot(fig)
    else:
        st.info("💡 탭 1에서 먼저 '🚀 분석 실행'을 진행해주세요.")

# ---------------------------------------------------------
# TAB 3: 매매 복기일지
# ---------------------------------------------------------
with tab3:
    st.markdown("### 📝 매매 복기 및 차트 저장 게시판")
    
    NOTE_FILE = "trade_notes.json"

    def load_notes():
        if os.path.exists(NOTE_FILE):
            with open(NOTE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save_notes(notes):
        with open(NOTE_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=4)

    notes = load_notes()

    with st.form("note_form", clear_on_submit=True):
        col_n1, col_n2 = st.columns([2, 2])
        with col_n1:
            note_date = st.date_input("매매일자", datetime.today())
            note_stock = st.text_input("종목명")
        with col_n2:
            note_type = st.selectbox("매매구분", ["매수복기", "매도복기", "관심종목분석", "일반노트"])
            uploaded_file = st.file_uploader("차트 이미지 첨부", type=["png", "jpg", "jpeg"])
        
        note_content = st.text_area("복기 내용 작성", height=120)
        submit_btn = st.form_submit_button("💾 일지 저장")

        if submit_btn:
            img_b64 = ""
            if uploaded_file is not None:
                img_bytes = uploaded_file.read()
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            new_note = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                "date": note_date.strftime("%Y-%m-%d"),
                "stock": note_stock,
                "type": note_type,
                "content": note_content,
                "image": img_b64
            }
            notes.insert(0, new_note)
            save_notes(notes)
            st.success("매매일지가 저장되었습니다!")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📖 저장된 매매일지 목록")

    if notes:
        for idx, note in enumerate(notes):
            with st.expander(f"[{note['date']}] {note['stock']} ({note['type']})"):
                st.write(f"**내용:** {note['content']}")
                if note.get("image"):
                    st.image(base64.b64decode(note["image"]))
                if st.button("🗑️ 삭제", key=f"del_{note['id']}"):
                    notes.pop(idx)
                    save_notes(notes)
                    st.success("삭제되었습니다.")
                    st.rerun()
    else:
        st.caption("저장된 매매일지가 없습니다.")
