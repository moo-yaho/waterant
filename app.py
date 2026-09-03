# 화면 출력용 데이터프레임 (숫자형으로 강제 변환하여 콤마가 정상 출력되도록 처리)
        for col in ["시가총액(억)", "현재가(원)", "거래대금(억)", "종목수익률(%)", "거래량 비율(%)", "상대강도(%)"]:
            if col in df_res.columns:
                df_res[col] = pd.to_numeric(df_res[col], errors='coerce')

# [여기에 붙여넣기] 화면에 표를 띄우기 전에 데이터를 먼저 콤마 낀 문자열로 변환합니다.
        df_display = df_res[display_cols].copy()

        # 시가총액, 현재가, 거래대금에 천 단위 콤마(,) 넣기
        int_cols = ["시가총액(억)", "현재가(원)", "거래대금(억)"]
        for col in int_cols:
            if col in df_display.columns:
                df_display[col] = pd.to_numeric(df_display[col], errors='coerce').fillna(0).astype(int).map('{:,}'.format)

        # 수익률 같은 소수점 컬럼 포맷 맞추기
        float_cols = ["종목수익률(%)", "거래량 비율(%)", "상대강도(%)"]
        for col in float_cols:
            if col in df_display.columns:
                df_display[col] = pd.to_numeric(df_display[col], errors='coerce').fillna(0).map('{:.2f}%'.format)

        # 화면에 출력
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True
        )
