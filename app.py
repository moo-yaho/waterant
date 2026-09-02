import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(page_title="주식 상대강도(RS) & 눌림목 스크리너", layout="wide")

st.title("📈 주식 상대강도(RS) 및 조건별 스크리너")

# ==========================================
# 1. 기존 핵심 설정 (100% 보존)
# ==========================================
st.sidebar.header("⚙️ 기본 스크리닝 설정")

index_choice = st.sidebar.selectbox(
    "기준 지수 선택",
    ["KOSPI", "KOSDAQ", "KOSPI+KOSDAQ"],
    index=0
)

period_num = st.sidebar.number_input("기간 숫자 입력", min_value=1, value=20, step=1)
period_unit = st.sidebar.selectbox("기간 단위", ["일", "주", "월"], index=0)
market_target = st.sidebar.selectbox("대상 시장", ["전체", "KOSPI", "KOSDAQ"], index=0)

# ==========================================
# 2. 새로 추가된 상세 입력 필터 (이상 ~ 이하)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.header("🔍 상세 필터 옵션 (비워두면 제한없음)")

# 분석 속도 향상을 위한 상위 N개 제한
top_n_limit = st.sidebar.number_input(
    "시가총액 상위 N개 제한 (0은 전종목)",
    min_value=0,
    value=300,
    step=50,
    help="장중 빠른 스크리닝을 위해 시가총액 상위 N개 종목만 1차 추출 후 분석합니다."
)

col_mcap1, col_mcap2 = st.sidebar.columns(2)
with col_mcap1:
    min_mcap = st.number_input("최소 시가총액(억)", min_value=0.0, value=0.0, step=100.0)
with col_mcap2:
    max_mcap = st.number_input("최대 시가총액(억)", min_value=0.0, value=0.0, step=100.0)

col_price1, col_price2 = st.sidebar.columns(2)
with col_price1:
    min_price = st.number_input("최소 현재가(원)", min_value=0, value=0, step=500)
with col_price2:
    max_price = st.number_input("최대 현재가(원)", min_value=0, value=0, step=500)

col_vol_amt1, col_vol_amt2 = st.sidebar.columns(2)
with col_vol_amt1:
    min_amount = st.number_input("최소 거래대금(억)", min_value=0.0, value=0.0, step=10.0)
with col_vol_amt2:
    max_amount = st.number_input("최대 거래대금(억)", min_value=0.0, value=0.0, step=10.0)

col_rs1, col_rs2 = st.sidebar.columns(2)
with col_rs1:
    min_rs = st.number_input("최소 RS(%)", min_value=-100.0, value=0.0, step=1.0)
with col_rs2:
    max_rs = st.number_input("최대 RS(%)", min_value=-100.0, value=0.0, step=1.0)

st.sidebar.subheader("📉 거래량 급감 필터")
vol_lookback_days = st.sidebar.number_input("과거 최고 거래량 조회 기간(일)", min_value=2, value=5, step=1)

col_vol_ratio1, col_vol_ratio2 = st.sidebar.columns(2)
with col_vol_ratio1:
    min_vol_ratio = st.number_input("최소 거래량비율(%)", min_value=0.0, value=0.0, step=5.0)
with col_vol_ratio2:
    max_vol_ratio = st.number_input("최대 거래량비율(%)", min_value=0.0, value=0.0, step=5.0)

# ==========================================
# 3. 데이터 계산 및 스크리닝 로직
# ==========================================

# 날짜 계산 함수
def get_start_date(num, unit):
    today = datetime.now()
    if unit == "일":
        start = today - timedelta(days=num * 2) # 여유 있게 트레이딩일 확보
    elif unit == "주":
        start = today - timedelta(weeks=num * 2)
    elif unit == "월":
        start = today - timedelta(days=num * 40)
    return start.strftime("%Y-%m-%d")

start_date = get_start_date(period_num, period_unit)

if st.button("🚀 분석", type="primary"):
    with st.spinner("시장 데이터 및 종목별 상대강도를 분석 중입니다..."):
        try:
            # 1. 기준 지수 데이터 수집
            if index_choice == "KOSPI":
                idx_df = fdr.DataReader("KS11", start_date)
            elif index_choice == "KOSDAQ":
                idx_df = fdr.DataReader("KQ11", start_date)
            else: # KOSPI+KOSDAQ 혼합 시 KOSPI를 기본 지수로 설정
                idx_df = fdr.DataReader("KS11", start_date)
                
            idx_return = ((idx_df["Close"].iloc[-1] - idx_df["Close"].iloc[0]) / idx_df["Close"].iloc[0]) * 100

            # 2. 전 종목 리스트 수집
            krx_df = fdr.StockListing("KRX")

            # 시장 구분 필터링
            if market_target == "KOSPI":
                krx_df = krx_df[krx_df["Market"] == "KOSPI"]
            elif market_target == "KOSDAQ":
                krx_df = krx_df[krx_df["Market"] == "KOSDAQ"]

            # 시가총액 순 정렬 및 N개 제한 적용
            krx_df = krx_df.sort_values(by="Marcap", ascending=False)
            if top_n_limit > 0:
                krx_df = krx_df.head(top_n_limit)

            results = []

            # 3. 개별 종목 수집 및 조건 판별
            for _, row in krx_df.iterrows():
                code = row["Code"]
                name = row["Name"]
                market = row["Market"]
                marcap_billion = row["Marcap"] / 100000000 # 원 -> 억원 변환

                # 종목 가격 데이터 수집
                stock_df = fdr.DataReader(code, start_date)
                if len(stock_df) < 2:
                    continue

                close_price = stock_df["Close"].iloc[-1]
                volume_amount_billion = (stock_df["Amount"].iloc[-1]) / 100000000 if "Amount" in stock_df.columns else (close_price * stock_df["Volume"].iloc[-1]) / 100000000

                # 종목 수익률 및 RS 계산 (기존 로직 유지)
                stock_return = ((close_price - stock_df["Close"].iloc[0]) / stock_df["Close"].iloc[0]) * 100
                rs_score = stock_return - idx_return

                # 눌림목 거래량 비율 계산 (최근 N일 최고 거래량 대비 오늘 거래량)
                recent_vol_df = stock_df.tail(vol_lookback_days)
                max_vol_recent = recent_vol_df["Volume"].max()
                today_vol = stock_df["Volume"].iloc[-1]
                
                vol_ratio = (today_vol / max_vol_recent * 100) if max_vol_recent > 0 else 100.0

                # ==========================================
                # 4. 필터링 판별 (비워두거나 0일 시 통과)
                # ==========================================
                if min_mcap > 0 and marcap_billion < min_mcap: continue
                if max_mcap > 0 and marcap_billion > max_mcap: continue

                if min_price > 0 and close_price < min_price: continue
                if max_price > 0 and close_price > max_price: continue

                if min_amount > 0 and volume_amount_billion < min_amount: continue
                if max_amount > 0 and volume_amount_billion > max_amount: continue

                if min_rs != 0.0 and rs_score < min_rs: continue
                if max_rs != 0.0 and rs_score > max_rs: continue

                if min_vol_ratio > 0 and vol_ratio < min_vol_ratio: continue
                if max_vol_ratio > 0 and vol_ratio > max_vol_ratio: continue

                # 조건 통과 종목 저장
                results.append({
                    "시장": market,
                    "종목명": name,
                    "시가총액(억)": marcap_billion,
                    "현재가(원)": close_price,
                    "거래대금(억)": volume_amount_billion,
                    "거래량 비율(%)": vol_ratio,
                    "종목수익률(%)": stock_return,
                    "상대강도(%)": rs_score
                })

            # ==========================================
            # 5. 결과 가독성 표출 처리
            # ==========================================
            if results:
                res_df = pd.DataFrame(results)
                
                # 상대강도 기준 내림차순 정렬
                res_df = res_df.sort_values(by="상대강도(%)", ascending=False).reset_index(drop=True)

                st.success(f"총 {len(res_df)}개 종목이 스크리닝 조건에 포착되었습니다.")

                # 트레이딩 가독성 포맷팅 적용 (천 단위 콤마 + 소수점 정리)
                formatted_df = res_df.copy()
                formatted_df["시가총액(억)"] = formatted_df["시가총액(억)"].map("{:,.0f}".format)
                formatted_df["현재가(원)"] = formatted_df["현재가(원)"].map("{:,.0f}".format)
                formatted_df["거래대금(억)"] = formatted_df["거래대금(억)"].map("{:,.1f}".format)
                formatted_df["거래량 비율(%)"] = formatted_df["거래량 비율(%)"].map("{:.1f}%".format)
                formatted_df["종목수익률(%)"] = formatted_df["종목수익률(%)"].map("{:+.2f}%".format)
                formatted_df["상대강도(%)"] = formatted_df["상대강도(%)"].map("{:+.2f}%".format)

                # 최종 테이블 출력
                st.dataframe(formatted_df, use_container_width=True)

            else:
                st.warning("조건에 해당하는 종목이 없습니다. 필터 범위를 조금 더 넓혀보세요.")

        except Exception as e:
            st.error(f"스크리닝 도중 오류가 발생했습니다: {e}")
