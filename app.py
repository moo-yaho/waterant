import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(page_title="주식 상대강도(RS) & 눌림목 스크리너", layout="wide")

st.title("📈 주식 상대강도(RS) 및 대시보드")

# ==========================================
# 1. 사이드바 설정 (스크리닝 조건)
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

st.sidebar.markdown("---")
st.sidebar.header("🔍 상세 필터 옵션 (비워두면 제한없음)")

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
# 2. 탭 구성 (스크리너 / 종목 분석 / 게시판 및 일지)
# ==========================================
tab1, tab2, tab3 = st.tabs(["🔎 종목 스크리너", "📊 종목 상세 분석", "📝 게시판 & 매매일지"])

# ------------------------------------------
# TAB 1: 종목 스크리너
# ------------------------------------------
with tab1:
    st.subheader("🚀 종목 스크리닝 실행")

    def get_start_date(num, unit):
        today = datetime.now()
        if unit == "일":
            start = today - timedelta(days=num * 2)
        elif unit == "주":
            start = today - timedelta(weeks=num * 2)
        elif unit == "월":
            start = today - timedelta(days=num * 40)
        return start.strftime("%Y-%m-%d")

    start_date = get_start_date(period_num, period_unit)

    if st.button("🚀 분석 실행", type="primary"):
        with st.spinner("시장 데이터 및 종목별 상대강도를 분석 중입니다..."):
            try:
                # 1. 지수 데이터
                if index_choice == "KOSPI":
                    idx_df = fdr.DataReader("KS11", start_date)
                elif index_choice == "KOSDAQ":
                    idx_df = fdr.DataReader("KQ11", start_date)
                else:
                    idx_df = fdr.DataReader("KS11", start_date)
                
                idx_return = ((idx_df["Close"].iloc[-1] - idx_df["Close"].iloc[0]) / idx_df["Close"].iloc[0]) * 100

                # 2. 종목 리스트
                krx_df = fdr.StockListing("KRX")

                if market_target == "KOSPI":
                    krx_df = krx_df[krx_df["Market"] == "KOSPI"]
                elif market_target == "KOSDAQ":
                    krx_df = krx_df[krx_df["Market"] == "KOSDAQ"]

                krx_df = krx_df.sort_values(by="Marcap", ascending=False)
                if top_n_limit > 0:
                    krx_df = krx_df.head(top_n_limit)

                results = []

                # 3. 개별 종목 분석
                for _, row in krx_df.iterrows():
                    code = row["Code"]
                    name = row["Name"]
                    market = row["Market"]
                    marcap_billion = row["Marcap"] / 100000000

                    stock_df = fdr.DataReader(code, start_date)
                    if len(stock_df) < 2:
                        continue

                    close_price = stock_df["Close"].iloc[-1]
                    volume_amount_billion = (stock_df["Amount"].iloc[-1]) / 100000000 if "Amount" in stock_df.columns else (close_price * stock_df["Volume"].iloc[-1]) / 100000000

                    stock_return = ((close_price - stock_df["Close"].iloc[0]) / stock_df["Close"].iloc[0]) * 100
                    rs_score = stock_return - idx_return

                    recent_vol_df = stock_df.tail(vol_lookback_days)
                    max_vol_recent = recent_vol_df["Volume"].max()
                    today_vol = stock_df["Volume"].iloc[-1]
                    
                    vol_ratio = (today_vol / max_vol_recent * 100) if max_vol_recent > 0 else 100.0

                    # 필터링
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

                if results:
                    res_df = pd.DataFrame(results)
                    res_df = res_df.sort_values(by="상대강도(%)", ascending=False).reset_index(drop=True)

                    st.success(f"총 {len(res_df)}개 종목이 스크리닝 조건에 포착되었습니다.")

                    formatted_df = res_df.copy()
                    formatted_df["시가총액(억)"] = formatted_df["시가총액(억)"].map("{:,.0f}".format)
                    formatted_df["현재가(원)"] = formatted_df["현재가(원)"].map("{:,.0f}".format)
                    formatted_df["거래대금(억)"] = formatted_df["거래대금(억)"].map("{:,.1f}".format)
                    formatted_df["거래량 비율(%)"] = formatted_df["거래량 비율(%)"].map("{:.1f}%".format)
                    formatted_df["종목수익률(%)"] = formatted_df["종목수익률(%)"].map("{:+.2f}%".format)
                    formatted_df["상대강도(%)"] = formatted_df["상대강도(%)"].map("{:+.2f}%".format)

                    st.dataframe(formatted_df, use_container_width=True)
                else:
                    st.warning("조건에 해당하는 종목이 없습니다. 필터 범위를 넓혀보세요.")

            except Exception as e:
                st.error(f"스크리닝 도중 오류가 발생했습니다: {e}")

# ------------------------------------------
# TAB 2: 종목 상세 분석
# ------------------------------------------
with tab2:
    st.subheader("📊 종목 차트 및 상세 분석")
    search_symbol = st.text_input("종목코드 또는 종목명 입력 (예: 005930 또는 삼성전자)", value="005930")
    
    if search_symbol:
        try:
            target_df = fdr.DataReader(search_symbol, start_date)
            if not target_df.empty:
                st.line_chart(target_df["Close"])
                st.dataframe(target_df.tail(10), use_container_width=True)
            else:
                st.info("해당 종목의 데이터가 없습니다.")
        except Exception as e:
            st.info("종목 코드를 입력하시면 차트와 과거 시세를 조회할 수 있습니다.")

# ------------------------------------------
# TAB 3: 게시판 및 매매일지 (JSON 자동 연동)
# ------------------------------------------
with tab3:
    st.subheader("📝 관망 노트 & 게시판")
    
    DATA_FILE = "trade_notes.json"

    # 기존 저장된 데이터 불러오기
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                notes = json.load(f)
        except Exception:
            notes = []
    else:
        notes = []

    # 글 작성 폼
    with st.form("note_form", clear_on_submit=True):
        author = st.text_input("작성자", value="익명")
        title = st.text_input("제목 (종목명 등)")
        content = st.text_area("내용 및 분석 메모")
        submitted = st.form_submit_button("글 쓰기")
        
        if submitted and title and content:
            new_note = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "author": author,
                "title": title,
                "content": content
            }
            notes.insert(0, new_note)
            
            # JSON 파일 저장
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(notes, f, ensure_ascii=False, indent=4)
                
            st.success("게시글이 성공적으로 저장되었습니다!")
            st.rerun()

    st.markdown("---")
    st.subheader("📌 작성된 게시글 목록")

    # 게시판 글 출력
    if notes:
        for idx, note in enumerate(notes):
            with st.expander(f"[{note.get('date', '')}] {note.get('title', '')} - (작성자: {note.get('author', '익명')})"):
                st.write(note.get("content", ""))
    else:
        st.info("아직 작성된 게시글이 없습니다. 위 폼을 이용해 일지나 메모를 남겨보세요.")
