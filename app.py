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
# [탭 1] 상대강도 스크리닝 (분석 및 검색)
# -------------------------------------------------------------------------
with tab1:
    st.subheader("1. 시장 대비 상대강도 스크리닝")

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
        market_options = {
            "KRX (전체)": "KRX",
            "KOSPI": "KOSPI",
            "KOSDAQ": "KOSDAQ",
        }
        selected_market_label = st.selectbox(
            "대상 시장", list(market_options.keys())
        )
        market_type = market_options[selected_market_label]

    # 날짜 계산 로직
    today = datetime.today()
    if "일 전" in period_unit:
        delta_days = period_num
    elif "주 전" in period_unit:
        delta_days = period_num * 7
    else:
        delta_days = period_num * 30

    start_date = (today - timedelta(days=delta_days)).strftime("%Y-%m-%d")

    if st.button("🚀 분석 실행", type="primary"):
        with st.spinner("시장 데이터와 전 종목을 분석 중입니다... 잠시만 기다려주세요."):
            df_bench = get_market_data(benchmark_code, start_date)
            if df_bench is None or df_bench.empty:
                st.error(
                    "기준 지수 데이터를 가져오는 데 실패했습니다. 날짜를 조정해 보세요."
                )
            else:
                try:
                    df_krx = fdr.StockListing(market_type)
                except Exception:
                    df_krx = fdr.StockListing("KRX-MARCAP") if market_type == "KRX" else fdr.StockListing("KRX")

                df_bench_filtered = df_bench[df_bench.index >= start_date]
                if len(df_bench_filtered) < 2:
                    st.warning(
                        "선택한 기간 내에 데이터 거래일이 너무 적습니다. 기간을 늘려주세요."
                    )
                else:
                    base_bench_price = df_bench_filtered["Close"].iloc[0]
                    curr_bench_price = df_bench_filtered["Close"].iloc[-1]
                    bench_growth = (
                        curr_bench_price / base_bench_price
                    ) - 1.0

                    results = []
                    target_stocks = df_krx.head(150)

                    for idx, row in target_stocks.iterrows():
                        code = row["Code"]
                        name = row["Name"]
                        df_stock = get_market_data(code, start_date)

                        if df_stock is not None and not df_stock.empty:
                            df_s_filtered = df_stock[
                                df_stock.index >= start_date
                            ]
                            if len(df_s_filtered) >= 2:
                                s_base = df_s_filtered["Close"].iloc[0]
                                s_curr = df_s_filtered["Close"].iloc[-1]
                                stock_growth = (s_base > 0) and (
                                    (s_curr / s_base) - 1.0
                                ) or 0.0

                                stock_factor = s_curr / s_base
                                bench_factor = (
                                    curr_bench_price / base_bench_price
                                )
                                rel_strength = (
                                    (stock_factor / bench_factor) - 1.0
                                ) * 100.0

                                trading_val = (
                                    df_s_filtered["Close"].iloc[-1]
                                    * df_s_filtered["Volume"].iloc[-1]
                                )

                                results.append(
                                    {
                                        "종목코드": code,
                                        "종목명": name,
                                        "현재가": s_curr,
                                        "거래대금(원)": trading_val,
                                        "상대강도(%)": round(
                                            rel_strength, 2
                                        ),
                                        "종목수익률(%)": round(
                                            stock_growth * 100, 2
                                        ),
                                    }
                                )

                    if results:
                        df_result = pd.DataFrame(results)
                        st.session_state["analysis_result"] = df_result
                        st.success(
                            f"분석 완료! 총 {len(df_result)}개 종목이 스크리닝되었습니다."
                        )
                    else:
                        st.warning("조건에 맞는 종목 데이터를 찾지 못했습니다.")

    if "analysis_result" in st.session_state:
        st.markdown("---")
        st.subheader("🛠️ 다중 복합 필터 및 정렬 패널")

        df_res = st.session_state["analysis_result"]

        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            min_rs = st.number_input(
                "상대강도 최소값 (%) 이상", value=0.0, step=5.0
            )
        with f_col2:
            min_val = st.number_input(
                "거래대금 최소값 이상 (원)",
                value=1000000000,
                step=500000000,
                format="%d",
            )
        with f_col3:
            min_price = st.number_input("현재가 최소값 이상 (원)", value=1000, step=500)

        filtered_df = df_res[
            (df_res["상대강도(%)"] >= min_rs)
            & (df_res["거래대금(원)"] >= min_val)
            & (df_res["현재가"] >= min_price)
        ]

        s_col1, s_col2 = st.columns(2)
        with s_col1:
            sort_by = st.selectbox(
                "정렬 기준 컬럼", ["상대강도(%)", "거래대금(원)", "종목수익률(%)", "현재가"]
            )
        with s_col2:
            ascending_opt = st.radio(
                "정렬 방향", ["오름차순", "내림차순"], index=1
            )

        is_ascending = True if ascending_opt == "오름차순" else False
        filtered_df = filtered_df.sort_values(by=sort_by, ascending=is_ascending)

        st.markdown(
            f"**검색 결과: 총 {len(filtered_df)}개 종목 (중복 조건 적용됨)**"
        )
        st.dataframe(filtered_df, use_container_width=True)


# -------------------------------------------------------------------------
# [탭 2] 종목 상세 및 추이 차트 (2단 분리 차트)
# -------------------------------------------------------------------------
with tab2:
    st.subheader("2. 종목별 상세 추이 분석 (2단 비교 차트)")

    if "analysis_result" in st.session_state:
        df_target = st.session_state["analysis_result"]
        selected_name = st.selectbox(
            "분석할 종목 선택", df_target["종목명"].tolist()
        )

        if selected_name:
            target_row = df_target[df_target["종목명"] == selected_name].iloc[
                0
            ]
            t_code = target_row["종목코드"]

            st.write(
                f"**선택 종목:** {selected_name} ({t_code}) | **현재가:** {target_row['현재가']:,}원 | **상대강도:** {target_row['상대강도(%)']}%"
            )

            if st.button("📊 상세 추이 차트 그리기"):
                with st.spinner("차트 데이터를 계산 중입니다..."):
                    df_s = get_market_data(t_code, start_date)
                    df_b = get_market_data(benchmark_code, start_date)

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
                            rs_trend = (
                                (stock_factor / bench_factor) - 1.0
                            ) * 100

                            fig, (ax1, ax2) = plt.subplots(
                                2, 1, figsize=(10, 8), sharex=True
                            )

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
                                label=f"{selected_idx_name} (지수)",
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
                            st.error(
                                "해당 기간의 공통 거래일 데이터가 부족합니다."
                            )
    else:
        st.info(
            "먼저 [탭 1]에서 '분석 실행'을 진행하여 종목 리스트를 생성해 주세요."
        )


# -------------------------------------------------------------------------
# [탭 3] 매매 복기 및 차트 게시판 (메모장 + 이미지 + 백업)
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
