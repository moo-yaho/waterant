import base64
from datetime import datetime, timedelta
import io
import json
import os
import FinanceDataReader as fdr
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

# 한글 폰트 설정 (Windows / Mac)
plt.rcParams['font.family'] = 'Malgun Gothic' if os.name == 'nt' else 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# --- 1. 페이지 설정 및 디자인 세팅 ---
st.set_page_config(
    page_title="개인 트레이딩 분석 & 일지 툴", page_icon="📈", layout="wide"
)

st.title("📈 개인 주도주 분석 & 매매 일지 시스템")
st.markdown(
    "시장 지수 대비 강력한 주도주를 발굴하고, 차트와 함께 매매 복기를 기록하는 나만의 프라이빗 툴입니다."
)

# --- 2. 로컬 저장 파일 경로 설정 ---
NOTE_FILE = "trade_notes.json"


# --- 3. 데이터 및 메모 관리 함수들 ---
@st.cache_data(ttl=3600)
def get_market_data(symbol, start_date):
    """지수 및 종목 데이터를 불러오는 함수"""
    try:
        df = fdr.DataReader(symbol, start_date)
        if df.empty:
            return None
        return df
    except Exception:
        return None


def load_notes():
    """저장된 메모(일지) 불러오기"""
    if os.path.exists(NOTE_FILE):
        try:
            with open(NOTE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_notes(notes):
    """메모(일지) 저장하기"""
    with open(NOTE_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=4)


# --- 4. 탭 구성 ---
tab1, tab2, tab3 = st.tabs(
    ["📊 상대강도 스크리닝", "🔍 종목 상세 및 추이 차트", "📝 매매 복기 일지"]
)

# -------------------------------------------------------------------------
# [탭 1] 상대강도 스크리닝 (분석 및 상세 필터)
# -------------------------------------------------------------------------
with tab1:
    st.subheader("1. 시장 대비 상대강도 스크리닝")

    # --- ① 기본 설정 패널 ---
    st.markdown("##### ⚙️ 기본 설정")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        index_options = {
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

    with col2:
        period_num = st.number_input(
            "기간 숫자 입력", min_value=1, max_value=365, value=4
        )

    with col3:
        period_unit = st.selectbox(
            "기간 단위", ["일 전 (Calendar Days)", "주 전", "개월 전"]
        )

    with col4:
        market_type = st.selectbox(
            "대상 시장", ["KRX (전체)", "KOSPI", "KOSDAQ"]
        )

    # 날짜 계산 로직
    today = datetime.today()
    if "일 전" in period_unit:
        delta_days = period_num
    elif "주 전" in period_unit:
        delta_days = period_num * 7
    else:  # 개월 전
        delta_days = period_num * 30

    start_date = (today - timedelta(days=delta_days)).strftime("%Y-%m-%d")

    # --- ② 상세 필터 패널 ---
    st.markdown("---")
    st.markdown("##### 🛠️ 상세 필터 설정 (미입력/0 입력 시 제한 없음)")

    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        top_n = st.number_input(
            "상위 N개 분석 제한 (시총 기준)", min_value=0, value=300, step=50, help="0 입력 시 대상 시장 전체 분석"
        )
    with f_col2:
        mc_min = st.number_input("시가총액 최소 (억 원)", min_value=0, value=0, step=100)
    with f_col3:
        mc_max = st.number_input("시가총액 최대 (억 원)", min_value=0, value=0, step=100)

    f_col4, f_col5, f_col6 = st.columns(3)
    with f_col4:
        price_min = st.number_input("현재가 최소 (원)", min_value=0, value=0, step=500)
    with f_col5:
        price_max = st.number_input("현재가 최대 (원)", min_value=0, value=0, step=1000)
    with f_col6:
        val_min = st.number_input("당일 거래대금 최소 (억 원)", min_value=0, value=0, step=10)

    f_col7, f_col8, f_col9 = st.columns(3)
    with f_col7:
        val_max = st.number_input("당일 거래대금 최대 (억 원)", min_value=0, value=0, step=10)
    with f_col8:
        rs_min = st.number_input("상대강도(RS) 최소 (%)", value=0.0, step=1.0)
    with f_col9:
        rs_max = st.number_input("상대강도(RS) 최대 (%)", value=0.0, step=1.0)

    f_col10, f_col11 = st.columns(2)
    with f_col10:
        vol_ratio_min = st.number_input("최고 거래량 대비 당일 거래량 비율 최소 (%)", value=0.0, step=5.0)
    with f_col11:
        vol_ratio_max = st.number_input("최고 거래량 대비 당일 거래량 비율 최대 (%)", value=0.0, step=5.0)

    st.markdown("---")

    # --- ③ 스크리닝 실행 ---
    if st.button("🚀 분석 실행", type="primary"):
        with st.spinner("시장 데이터와 종목을 분석 중입니다... 잠시만 기다려주세요."):
            df_bench = get_market_data(benchmark_code, start_date)
            if df_bench is None or df_bench.empty:
                st.error("기준 지수 데이터를 가져오는 데 실패했습니다. 날짜를 조정해 보세요.")
            else:
                st.session_state["benchmark_code"] = benchmark_code
                st.session_state["selected_idx_name"] = selected_idx_name
                st.session_state["start_date"] = start_date

                target_market = "KRX" if "전체" in market_type else market_type
                df_krx = fdr.StockListing(target_market)

                # 상위 N개 분석 제한 처리
                if top_n > 0:
                    df_krx = df_krx.head(top_n)

                df_bench_filtered = df_bench[df_bench.index >= start_date]
                if len(df_bench_filtered) < 2:
                    st.warning("선택한 기간 내에 데이터 거래일이 너무 적습니다. 기간을 늘려주세요.")
                else:
                    base_bench_price = df_bench_filtered["Close"].iloc[0]
                    curr_bench_price = df_bench_filtered["Close"].iloc[-1]

                    results = []

                    for idx, row in df_krx.iterrows():
                        code = row["Code"]
                        name = row["Name"]
                        mkt = row.get("Market", target_market)
                        marcap = row.get("Marcap", 0)  # 시가총액 (원 단위)

                        df_stock = get_market_data(code, start_date)

                        if df_stock is not None and not df_stock.empty:
                            df_s_filtered = df_stock[df_stock.index >= start_date]
                            if len(df_s_filtered) >= 2:
                                s_base = df_s_filtered["Close"].iloc[0]
                                s_curr = df_s_filtered["Close"].iloc[-1]
                                stock_growth = ((s_curr / s_base) - 1.0) * 100.0 if s_base > 0 else 0.0

                                # 상대강도 계산 (원래 연산 로직 그대로)
                                stock_factor = s_curr / s_base
                                bench_factor = curr_bench_price / base_bench_price
                                rel_strength = ((stock_factor / bench_factor) - 1.0) * 100.0

                                # 당일 거래대금 (원 단위)
                                trading_val = s_curr * df_s_filtered["Volume"].iloc[-1]

                                # 최근 N일 최고 거래량 대비 당일 거래량 비율 (%)
                                max_vol = df_s_filtered["Volume"].max()
                                curr_vol = df_s_filtered["Volume"].iloc[-1]
                                vol_ratio = (curr_vol / max_vol * 100.0) if max_vol > 0 else 0.0

                                # 시가총액 및 거래대금 (억 원 단위 변환)
                                marcap_eok = marcap / 1e8 if marcap else 0
                                trading_val_eok = trading_val / 1e8

                                # --- 상세 필터링 판정 ---
                                if mc_min > 0 and marcap_eok < mc_min:
                                    continue
                                if mc_max > 0 and marcap_eok > mc_max:
                                    continue
                                if price_min > 0 and s_curr < price_min:
                                    continue
                                if price_max > 0 and s_curr > price_max:
                                    continue
                                if val_min > 0 and trading_val_eok < val_min:
                                    continue
                                if val_max > 0 and trading_val_eok > val_max:
                                    continue
                                if rs_min != 0.0 and rel_strength < rs_min:
                                    continue
                                if rs_max != 0.0 and rel_strength > rs_max:
                                    continue
                                if vol_ratio_min != 0.0 and vol_ratio < vol_ratio_min:
                                    continue
                                if vol_ratio_max != 0.0 and vol_ratio > vol_ratio_max:
                                    continue

                                # 최종 고정 컬럼 구성 (종목수익률과 거래량 비율 위치 변경 반영)
                                results.append(
                                    {
                                        "시장": mkt,
                                        "종목명": name,
                                        "시가총액(억)": f"{marcap_eok:,.0f}억" if marcap_eok > 0 else "-",
                                        "현재가(원)": f"{s_curr:,.0f}",
                                        "거래대금(억)": f"{trading_val_eok:,.0f}억",
                                        "종목수익률(%)": round(stock_growth, 2),
                                        "거래량 비율(%)": f"{vol_ratio:.1f}%",
                                        "상대강도(%)": round(rel_strength, 2),
                                        "_code": code,  # 차트 조회용 내부 고유코드
                                    }
                                )

                    if results:
                        df_result = pd.DataFrame(results)
                        st.session_state["analysis_result"] = df_result
                        st.success(f"분석 완료! 조건에 맞는 총 {len(df_result)}개 종목이 검색되었습니다.")
                    else:
                        st.warning("조건에 맞는 종목 데이터를 찾지 못했습니다.")

    # --- ④ 결과 표 출력 ---
    if "analysis_result" in st.session_state:
        df_res = st.session_state["analysis_result"]

        st.subheader("📋 스크리닝 결과 목록")
        # 차트용 내부 코드는 화면에 노출하지 않고 표시
        display_cols = [col for col in df_res.columns if col != "_code"]
        st.dataframe(df_res[display_cols], use_container_width=True)


# -------------------------------------------------------------------------
# [탭 2] 종목 상세 및 추이 차트 (2단 비교 차트)
# -------------------------------------------------------------------------
with tab2:
    st.subheader("2. 종목별 상세 추이 분석 (2단 비교 차트)")

    if "analysis_result" in st.session_state:
        df_target = st.session_state["analysis_result"]
        selected_name = st.selectbox(
            "분석할 종목 선택", df_target["종목명"].tolist()
        )

        if selected_name:
            target_row = df_target[df_target["종목명"] == selected_name].iloc[0]
            t_code = target_row["_code"]

            st.write(
                f"**선택 종목:** {selected_name} ({t_code}) | **현재가:** {target_row['현재가(원)']}원 | **상대강도:** {target_row['상대강도(%)']}%"
            )

            if st.button("📊 상세 추이 차트 그리기"):
                with st.spinner("차트 데이터를 계산 중입니다..."):
                    s_date = st.session_state.get("start_date", start_date)
                    b_code = st.session_state.get("benchmark_code", benchmark_code)
                    b_name = st.session_state.get("selected_idx_name", selected_idx_name)

                    df_s = get_market_data(t_code, s_date)
                    df_b = get_market_data(b_code, s_date)

                    if df_s is not None and df_b is not None:
                        common_idx = df_s.index.intersection(df_b.index)
                        df_s = df_s.loc[common_idx]
                        df_b = df_b.loc[common_idx]

                        if not df_s.empty:
                            s_start = df_s["Close"].iloc[0]
                            b_start = df_b["Close"].iloc[0]

                            stock_cum_ret = (df_s["Close"] / s_start - 1.0) * 100
                            bench_cum_ret = (df_b["Close"] / b_start - 1.0) * 100

                            stock_factor = df_s["Close"] / s_start
                            bench_factor = df_b["Close"] / b_start
                            rs_trend = ((stock_factor / bench_factor) - 1.0) * 100

                            fig, (ax1, ax2) = plt.subplots(
                                2, 1, figsize=(10, 8), sharex=True
                            )

                            # 상단 차트: 절대 누적 수익률 비교
                            ax1.plot(
                                common_idx,
                                stock_cum_ret,
                                label=f"{selected_name} (종목)",
                                color="crimson",
                                linewidth=2,
                            )
                            ax1.plot(
                                common_idx,
                                bench_cum_ret,
                                label=f"{b_name} (지수)",
                                color="dodgerblue",
                                linewidth=2,
                                linestyle="--",
                            )
                            ax1.set_title(
                                f"[{selected_name}] 절대 누적 수익률 비교 (%)"
                            )
                            ax1.set_ylabel("수익률 (%)")
                            ax1.legend()
                            ax1.grid(True, alpha=0.3)

                            # 하단 차트: 상대강도 비율 추이
                            ax2.plot(
                                common_idx,
                                rs_trend,
                                label="상대강도 추이 (초과 성과 %)",
                                color="forestgreen",
                                linewidth=2,
                            )
                            ax2.axhline(0, color="gray", linestyle=":", alpha=0.7)
                            ax2.set_title(
                                "상대강도 비율 추이 (우상향 = 주도력 강화)"
                            )
                            ax2.set_ylabel("상대강도 (%)")
                            ax2.set_xlabel("날짜")
                            ax2.legend()
                            ax2.grid(True, alpha=0.3)

                            plt.tight_layout()
                            st.pyplot(fig)
                        else:
                            st.error("해당 기간의 공통 거래일 데이터가 부족합니다.")
    else:
        st.info("먼저 [탭 1]에서 '분석 실행'을 진행하여 종목 리스트를 생성해 주세요.")


# -------------------------------------------------------------------------
# [탭 3] 매매 복기 및 차트 게시판 (메모장 + 이미지 + 백업)
# -------------------------------------------------------------------------
with tab3:
    st.subheader("3. 나만의 매매 일지 및 차트 복기 게시판")

    notes = load_notes()

    # 입력 폼
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
            "상세 내용 (진입 근거, 심리, 배운 점 등)",
            placeholder="자세한 일기를 적어보세요...",
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
            with st.expander(
                f"[{note['category']}] {note['date']} - {note['title']}"
            ):
                st.write(f"**작성일:** {note['date']}")
                st.write(f"**내용:**\n\n{note['content']}")

                if note.get("image"):
                    try:
                        img_bytes = base64.b64decode(note["image"])
                        st.image(
                            img_bytes,
                            caption="첨부된 차트 캡처",
                            use_column_width=True,
                        )
                    except Exception:
                        st.warning("이미지를 불러오는 중 오류가 발생했습니다.")

                if st.button("🗑️ 이 일지 삭제하기", key=f"del_{note['id']}"):
                    notes.pop(i)
                    save_notes(notes)
                    st.success("일지가 삭제되었습니다.")
                    st.rerun()
