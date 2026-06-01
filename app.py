import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from modules.krx_data import (
    get_hot_stocks_krx, get_stock_history, get_fundamentals,
    get_last_trading_date, search_krx_ticker
)
from modules.us_data import (
    get_hot_stocks_us, get_us_stock_history, get_us_fundamentals, get_us_news
)
from modules.news import get_naver_stock_news, get_naver_market_news, format_news_for_prompt
from modules.technical import get_indicators, interpret_signal
from modules.claude_analysis import analyze_single_stock, get_daily_top_picks, chat_with_analyst
from modules.email_report import send_daily_report, build_report_html
from modules.scanner import (
    scan_volume_anomaly, scan_breakout_imminent,
    scan_oversold, scan_pullback, scan_new_high
)
from modules.smart_picks import scan_smart_picks, build_smart_summary
from modules.claude_analysis import get_smart_picks_analysis

# ── 페이지 설정 ────────────────────────────────────────────────
st.set_page_config(
    page_title="하윤아빠 부자되기",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] { padding: 8px 14px; border-radius: 6px; }
.buy-badge { color: #a6e3a1; font-weight: bold; }
.sell-badge { color: #f38ba8; font-weight: bold; }
.hold-badge { color: #f9e2af; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# ── secrets에서 기본값 로드 ────────────────────────────────────
def _secret(key, fallback=""):
    try:
        return st.secrets.get(key, fallback)
    except Exception:
        return fallback

# API 키는 secrets에서 자동 로드
api_key = _secret("ANTHROPIC_API_KEY")
gmail_addr = _secret("GMAIL_ADDRESS")
gmail_pw = _secret("GMAIL_APP_PASSWORD")
recv_addr = _secret("RECV_EMAIL")

# ── 사이드바 ───────────────────────────────────────────────────
with st.sidebar:
    st.title("💰 하윤아빠 부자되기")
    st.caption(f"기준일: {get_last_trading_date()}")

    st.divider()
    market_filter = st.selectbox(
        "분석 시장",
        ["ALL (국내)", "KOSPI", "KOSDAQ", "미국"],
        index=0
    )
    top_n = st.slider("표시 종목 수", 10, 50, 20)

    st.divider()
    st.caption("⚠️ 투자 손실의 책임은 투자자 본인에게 있습니다.")


def get_market_code():
    m = market_filter
    if m == "ALL (국내)": return "ALL"
    if m == "미국": return "미국"
    return m


# ── 탭 ────────────────────────────────────────────────────────
tabs = st.tabs([
    "🔥 오늘 급등주",
    "💡 하윤이의 추천종목",
    "💎 하윤아빠의 추천종목",
    "📐 돌파 직전",
    "🔄 눌림목",
    "🔍 종목 분석",
    "💬 AI 챗",
])

tab_hot, tab_ai, tab_smart, tab_break, tab_pull, tab_stock, tab_chat = tabs


# ── 공통: 스캐너 결과 표시 함수 ────────────────────────────────
def show_scanner_result(df, description, key, highlight_col=None):
    if df is None or df.empty:
        st.info("조건에 맞는 종목이 없습니다. 필터 조건을 완화하거나 나중에 다시 시도해보세요.")
        return
    st.caption(f"총 {len(df)}개 종목 | {description}")
    try:
        if highlight_col and highlight_col in df.columns:
            st.dataframe(
                df.style.background_gradient(subset=[highlight_col], cmap="RdYlGn"),
                use_container_width=True, height=450
            )
        else:
            st.dataframe(df, use_container_width=True, height=450)
    except Exception:
        st.dataframe(df, use_container_width=True, height=450)


def run_button(label, key):
    col1, col2 = st.columns([1, 5])
    with col1:
        return st.button(label, key=key, type="primary", use_container_width=True)
    return False


# ══════════════════════════════════════════════════════════════
# TAB 1: 오늘 급등주
# ══════════════════════════════════════════════════════════════
with tab_hot:
    st.header("🔥 오늘의 급등주")
    st.markdown("""
    > **전략:** 급등주 자체를 매수하는 게 아니라,
    > **같은 테마의 아직 안 오른 종목**이나 **내일 눌림목**을 노리는 참고 자료로 활용
    """)

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        run_hot = st.button("스캔 시작", key="run_hot", type="primary", use_container_width=True)
    with col2:
        min_change = st.number_input("최소 등락률%", 0.0, 20.0, 2.0, 0.5, key="hot_chg")

    if run_hot or "hot_df" in st.session_state:
        if run_hot:
            with st.spinner("급등주 스캔 중..."):
                mkt = get_market_code()
                if mkt == "미국":
                    st.session_state.hot_df = get_hot_stocks_us(top_n=top_n)
                else:
                    st.session_state.hot_df = get_hot_stocks_krx(market=mkt, top_n=top_n)

        df = st.session_state.get("hot_df", pd.DataFrame())
        if not df.empty and "등락률" in df.columns:
            df = df[df["등락률"] >= min_change]

        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("급등 종목", f"{len(df)}개")
            c2.metric("평균 등락률", f"{df['등락률'].mean():.1f}%")
            c3.metric("최고 등락률", f"{df['등락률'].max():.1f}%")

            show_scanner_result(df, "등락률 + 거래량 기준", "hot", "등락률")

            # 막대차트
            name_col = "종목명" if "종목명" in df.columns else "티커"
            fig = go.Figure(go.Bar(
                x=df[name_col].head(15),
                y=df["등락률"].head(15),
                marker_color=["#a6e3a1" if v > 0 else "#f38ba8" for v in df["등락률"].head(15)],
                text=[f"{v:+.1f}%" for v in df["등락률"].head(15)],
                textposition="outside"
            ))
            fig.update_layout(title="등락률 Top 15", height=350,
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              xaxis_tickangle=-35)
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# TAB 3: 돌파 직전
# ══════════════════════════════════════════════════════════════
with tab_break:
    st.header("📐 돌파 직전")
    st.markdown("""
    > **골든크로스 발생** (MA5 > MA20) 또는 **52주 신고가 5% 이내** 접근
    > 추세가 막 전환되거나 저항선 돌파를 앞둔 구간
    """)
    st.info("💡 **활용법:** 골든크로스 발생 당일 또는 다음날 장 초반 매수 → 손절은 MA20 이탈 시")

    if run_button("돌파 직전 스캔", "run_break"):
        with st.spinner("분석 중..."):
            st.session_state.break_df = scan_breakout_imminent(get_market_code(), top_n)

    show_scanner_result(
        st.session_state.get("break_df"),
        "골든크로스 또는 52주 고점 5% 이내",
        "break", "점수"
    )


# ══════════════════════════════════════════════════════════════
# TAB 5: 눌림목
# ══════════════════════════════════════════════════════════════
with tab_pull:
    st.header("🔄 눌림목 매수")
    st.markdown("""
    > **20일 추세 +5%↑** 인데 최근 고점 대비 **-3~-15% 조정** 중
    > 추세는 살아있고 잠깐 쉬는 구간 = 원래 급등주를 **더 싸게 사는 기회**
    """)
    st.info("💡 **활용법:** MA20 위에서 거래량 줄며 조정 중 → 거래량 다시 터지면 매수 / MA20 이탈 시 손절")

    if run_button("눌림목 스캔", "run_pull"):
        with st.spinner("분석 중..."):
            st.session_state.pull_df = scan_pullback(get_market_code(), top_n)

    show_scanner_result(
        st.session_state.get("pull_df"),
        "추세 유지 + 고점 대비 -3~-15% 조정 중",
        "pull"
    )


# ══════════════════════════════════════════════════════════════
# TAB 7: AI 추천
# ══════════════════════════════════════════════════════════════
with tab_ai:
    st.header("💡 하윤이의 추천 종목")
    st.caption("전체 시장 스캔 후 주식천재 하윤이가 단타/스윙/중장기 추천 종목과 진입 전략·매수가·목표가·손절가를 제시합니다.")

    run_ai = st.button("🚀 하윤이 분석 시작 !", type="primary", use_container_width=False)

    if run_ai:
        mkt = get_market_code()
        summary_lines = []

        with st.spinner("1/4 급등주 스캔 중..."):
            hot = get_hot_stocks_us(top_n=20) if mkt == "미국" else get_hot_stocks_krx(market=mkt, top_n=20)
            st.session_state.hot_df = hot

        with st.spinner("2/4 거래량 이상 스캔 중..."):
            vol = scan_volume_anomaly(mkt, top_n)
            st.session_state.vol_df = vol

        with st.spinner("3/4 돌파직전·눌림목 스캔 중..."):
            brk = scan_breakout_imminent(mkt, top_n)
            pull = scan_pullback(mkt, top_n)
            st.session_state.break_df = brk
            st.session_state.pull_df = pull

        # 전체 요약 텍스트 생성 (현재가 포함)
        currency = "$" if mkt == "미국" else "원"
        price_map = {}  # 티커 → (현재가, currency) 저장
        for df, label in [(hot, "급등주"), (vol, "거래량이상"), (brk, "돌파직전"), (pull, "눌림목")]:
            if df is not None and not df.empty:
                name_col = "종목명" if "종목명" in df.columns else "티커"
                ticker_col = "티커" if "티커" in df.columns else name_col
                price_col = "종가" if "종가" in df.columns else ("현재가" if "현재가" in df.columns else None)
                for _, row in df.head(5).iterrows():
                    chg = row.get("등락률", "")
                    chg_str = f" 등락:{chg:.1f}%" if isinstance(chg, (int, float)) else ""
                    price = row.get(price_col) if price_col else None
                    price_str = f" 현재가:{price:,.0f}{currency}" if price else ""
                    ticker = row.get(ticker_col, "")
                    if price and ticker:
                        price_map[ticker] = (price, currency)
                    summary_lines.append(
                        f"[{label}] {row.get(name_col,'')}({ticker}){price_str}{chg_str}"
                    )
        st.session_state.price_map = price_map

        market_news = get_naver_market_news(5)
        with st.spinner("주식천재 하윤이가 분석중... (20~30초)"):
            result = get_daily_top_picks(api_key, "\n".join(summary_lines),
                                         format_news_for_prompt(market_news))
        st.session_state.ai_picks = result

    if "ai_picks" in st.session_state:
        picks = st.session_state.ai_picks
        if "오류" in picks:
            st.error(picks["오류"])
        else:
            if picks.get("시장요약"):
                st.info(f"📊 {picks['시장요약']}")
            if picks.get("오늘주의사항"):
                st.warning(f"⚠️ {picks['오늘주의사항']}")

            for pick in picks.get("추천종목", []):
                emoji = {"단타": "🔴", "스윙": "🟡", "중장기": "🟢"}.get(pick.get("전략", ""), "⚪")
                entry = pick.get("진입방법", "")
                entry_badge = {"지금바로": "🟢 지금바로", "눌림목대기": "⏳ 눌림목대기", "분할매수": "📊 분할매수"}.get(entry, entry)
                # 현재가 조회
                ticker = pick.get("티커", "")
                price_info = st.session_state.get("price_map", {}).get(ticker)
                current_price_str = ""
                if price_info:
                    cur_p, cur_c = price_info
                    current_price_str = f"  |  조회시 현재가: {cur_p:,.0f}{cur_c}"

                with st.expander(
                    f"{pick.get('순위','')}위 | **{pick.get('종목명','')}** "
                    f"({ticker}) {emoji} {pick.get('전략','')} "
                    f"| {entry_badge}  | 예상 {pick.get('예상수익률','')}{current_price_str}",
                    expanded=True
                ):
                    p1, p2, p3, p4 = st.columns(4)
                    if price_info:
                        p1.metric("📌 조회시 현재가", f"{price_info[0]:,.0f}{price_info[1]}")
                    else:
                        p1.metric("📌 조회시 현재가", "-")
                    p2.metric("💰 매수가", pick.get("매수가", "-"))
                    p3.metric("🎯 목표가", pick.get("목표가", "-"))
                    p4.metric("🛑 손절가", pick.get("손절가", "-"))
                    st.write(f"**추천 이유:** {pick.get('추천이유', '')}")
                    if pick.get("주의사항"):
                        st.caption(f"⚠️ {pick.get('주의사항', '')}")



# ══════════════════════════════════════════════════════════════
# TAB 💎: 하윤아빠의 추천종목
# ══════════════════════════════════════════════════════════════
with tab_smart:
    st.header("💎 하윤아빠의 추천종목")
    st.markdown("""
    > 급등주 추격 ❌ — **재무 퀄리티 + 기술적 셋업 + 뉴스 촉매** 3박자가 맞는 종목만
    > 단타 / 스윙 / 중장기 전략별로 각 2개씩, 총 6개 추천
    """)

    col1, col2 = st.columns([1, 4])
    with col1:
        run_smart = st.button("💎 분석 시작", type="primary", use_container_width=True)
    with col2:
        st.caption("전 종목을 단타/스윙/중장기 점수로 평가 → 70점↑ 후보만 Claude 심층 분석 → 전략별 최종 2개 선정")

    if run_smart:
        mkt = get_market_code()
        currency = "$" if mkt == "미국" else "원"

        with st.spinner("전 종목 점수 산출 중... (30~40초)"):
            picks_dict = scan_smart_picks(mkt, top_n=5)

        if "오류" in picks_dict:
            st.error(picks_dict["오류"])
        else:
            # 점수 결과 미리보기
            st.subheader("📊 전략별 점수 상위 후보")
            cols = st.columns(3)
            for i, (strategy, emoji) in enumerate([("단타", "🔴"), ("스윙", "🟡"), ("중장기", "🟢")]):
                df = picks_dict.get(strategy, pd.DataFrame())
                with cols[i]:
                    st.markdown(f"**{emoji} {strategy}**")
                    if not df.empty:
                        show = df[["종목명", "점수", "등락률", "RSI"]].copy()
                        st.dataframe(show, use_container_width=True, hide_index=True)
                    else:
                        st.caption("해당 없음")

            # Claude 심층 분석
            market_news = get_naver_market_news(5)
            summary = build_smart_summary(picks_dict, currency)

            with st.spinner("주식천재 하윤이가 심층 분석 중... (20~30초)"):
                result = get_smart_picks_analysis(api_key, summary,
                                                   format_news_for_prompt(market_news))
            st.session_state.smart_result = result

    if "smart_result" in st.session_state:
        result = st.session_state.smart_result
        if "오류" in result:
            st.error(result["오류"])
        else:
            if result.get("시장한줄요약"):
                st.info(f"📊 {result['시장한줄요약']}")

            st.divider()
            for strategy, emoji, color in [
                ("단타", "🔴", "#ff6b6b"),
                ("스윙", "🟡", "#ffd93d"),
                ("중장기", "🟢", "#6bcb77")
            ]:
                picks = result.get(strategy, [])
                if not picks:
                    continue
                st.markdown(f"### {emoji} {strategy} 추천")
                for pick in picks:
                    with st.expander(
                        f"**{pick.get('종목명','')}** ({pick.get('티커','')}) "
                        f"| 예상 {pick.get('예상수익률','')}",
                        expanded=True
                    ):
                        p1, p2, p3, p4 = st.columns(4)
                        p1.metric("📌 현재가", pick.get("현재가", "-"))
                        p2.metric("💰 매수가", pick.get("매수가", "-"))
                        p3.metric("🎯 목표가", pick.get("목표가", "-"))
                        p4.metric("🛑 손절가", pick.get("손절가", "-"))
                        st.write(f"**투자 근거:** {pick.get('투자근거', '')}")
                        st.caption(f"⚠️ 리스크: {pick.get('리스크', '')}")
                st.divider()


# ══════════════════════════════════════════════════════════════
# TAB 8: 종목 분석
# ══════════════════════════════════════════════════════════════
with tab_stock:
    st.header("🔍 종목 상세 분석")

    col_s, col_m = st.columns([3, 1])
    with col_s:
        search_input = st.text_input("종목명 또는 티커", placeholder="예: 삼성전자, 005930, NVDA")
    with col_m:
        search_market = st.selectbox("시장", ["국내 (KRX)", "미국 (US)"])

    if search_input:
        is_us = search_market == "미국 (US)"

        if is_us:
            ticker = search_input.upper().strip()
            fund = get_us_fundamentals(ticker)
            name = fund.get("종목명", ticker)
            hist = get_us_stock_history(ticker, period="3mo")
            news_list = get_us_news(ticker)
            currency = "$"
        else:
            results = search_krx_ticker(search_input)
            if not results:
                st.warning("종목을 찾을 수 없습니다.")
                st.stop()
            if len(results) > 1:
                opts = {f"{r['종목명']} ({r['티커']}) - {r['시장']}": r for r in results[:10]}
                sel = st.selectbox("종목 선택", list(opts.keys()))
                info = opts[sel]
            else:
                info = results[0]
            ticker = info["티커"]
            name = info["종목명"]
            mkt_krx = info["시장"]
            fund = get_fundamentals(ticker, mkt_krx)
            hist = get_stock_history(ticker, mkt_krx, days=90)
            news_list = get_naver_stock_news(ticker)
            currency = "원"

        if hist.empty:
            st.error("데이터를 불러올 수 없습니다.")
            st.stop()

        close_col = "Close" if "Close" in hist.columns else "종가"
        cur = float(hist[close_col].iloc[-1])
        prev = float(hist[close_col].iloc[-2]) if len(hist) > 1 else cur
        chg = (cur - prev) / prev * 100

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("종목명", name)
        c2.metric("현재가", f"{cur:,.0f}{currency}")
        c3.metric("등락률", f"{chg:+.2f}%")
        c4.metric("티커", ticker)

        indicators = get_indicators(hist)
        overall_signal, signal_list, score = interpret_signal(indicators)

        col_chart, col_ind = st.columns([2, 1])
        with col_chart:
            vol_col = "Volume" if "Volume" in hist.columns else "거래량"
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                row_heights=[0.7, 0.3], vertical_spacing=0.05)
            fig.add_trace(go.Candlestick(
                x=hist.index,
                open=hist.get("Open", hist.get("시가")),
                high=hist.get("High", hist.get("고가")),
                low=hist.get("Low", hist.get("저가")),
                close=hist[close_col],
                name="주가",
                increasing_line_color="#a6e3a1",
                decreasing_line_color="#f38ba8"
            ), row=1, col=1)
            if vol_col in hist.columns:
                fig.add_trace(go.Bar(
                    x=hist.index, y=hist[vol_col],
                    name="거래량", marker_color="rgba(137,180,250,0.5)"
                ), row=2, col=1)
            fig.update_layout(title=f"{name} ({ticker})", height=420,
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_ind:
            st.subheader("기술적 신호")
            badge = {"강한 매수": "buy-badge", "매수": "buy-badge",
                     "강한 매도": "sell-badge", "매도": "sell-badge"}.get(overall_signal, "hold-badge")
            st.markdown(f'<span class="{badge}" style="font-size:1.3em">{overall_signal}</span>',
                        unsafe_allow_html=True)
            for s in signal_list:
                st.caption(f"• {s}")
            st.divider()
            for k in ["RSI", "이동평균_5", "이동평균_20", "BB_상단", "BB_하단"]:
                v = indicators.get(k)
                if v:
                    st.metric(k, f"{v:,.1f}")

        if fund:
            st.subheader("재무 지표")
            cols = st.columns(min(len(fund), 5))
            for i, (k, v) in enumerate([x for x in fund.items() if x[0] != "종목명"]):
                cols[i % len(cols)].metric(k, str(v) if v else "N/A")

        if news_list:
            st.subheader("📰 최근 뉴스")
            for n in news_list:
                st.markdown(f"- [{n['제목']}]({n['링크']}) `{n.get('시간','')}`")

        st.divider()
        if not api_key:
            st.info("API 키 입력 시 AI 매수가/목표가/손절가 분석 가능")
        else:
            if st.button("🤖 주식천재 하윤이 심층 분석", type="primary"):
                with st.spinner("분석 중..."):
                    result = analyze_single_stock(api_key, {
                        "종목명": name, "시장": "미국" if is_us else "국내",
                        "현재가": cur, "등락률": chg,
                        "거래량비율": indicators.get("거래량비율_20MA", 1.0) or 1.0,
                        "기술적지표": indicators, "재무지표": fund,
                        "뉴스": format_news_for_prompt(news_list), "통화": currency,
                    })

                if "오류" in result:
                    st.error(result["오류"])
                else:
                    opinion = result.get("투자의견", "")
                    color = {"매수": "#a6e3a1", "매도": "#f38ba8"}.get(opinion, "#f9e2af")
                    st.markdown(
                        f"<h3 style='color:{color}'>AI 의견: {opinion} "
                        f"<small>(신뢰도: {result.get('신뢰도','')})</small></h3>",
                        unsafe_allow_html=True
                    )
                    st.info(f"**한줄 요약:** {result.get('한줄요약','')}")

                    p1, p2, p3 = st.columns(3)
                    bp = result.get("매수목표가", cur)
                    tp = result.get("목표주가", cur)
                    sp = result.get("손절가", cur)
                    p1.metric("매수 목표가", f"{bp:,.0f}{currency}",
                              delta=f"{(bp/cur-1)*100:.1f}%")
                    p2.metric("목표 주가", f"{tp:,.0f}{currency}",
                              delta=f"{(tp/cur-1)*100:.1f}%")
                    p3.metric("손절가", f"{sp:,.0f}{currency}",
                              delta=f"{(sp/cur-1)*100:.1f}%", delta_color="inverse")

                    ca, cb = st.columns(2)
                    with ca:
                        st.subheader("✅ 매수 근거")
                        for r in result.get("매수근거", []):
                            st.write(f"• {r}")
                        st.subheader("📈 단기 전망")
                        st.write(result.get("단기전망", ""))
                    with cb:
                        st.subheader("⚠️ 리스크")
                        for r in result.get("리스크요인", []):
                            st.write(f"• {r}")
                        st.subheader("📊 중기 전망")
                        st.write(result.get("중기전망", ""))


# ══════════════════════════════════════════════════════════════
# TAB 9: AI 챗
# ══════════════════════════════════════════════════════════════
with tab_chat:
    st.header("💬 AI 애널리스트 챗")

    if not api_key:
        st.warning("사이드바에서 API 키를 입력해주세요.")
    else:
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        st.caption("빠른 질문:")
        q_cols = st.columns(4)
        quick_qs = [
            "오늘 시장 분위기?",
            "반도체 섹터 전망?",
            "달러 강세일 때 전략?",
            "눌림목 매수 타이밍 잡는 법?",
        ]
        for i, qq in enumerate(quick_qs):
            if q_cols[i].button(qq, use_container_width=True, key=f"qq{i}"):
                st.session_state.quick_q = qq

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_input = st.chat_input("주식에 대해 무엇이든 물어보세요...")
        if "quick_q" in st.session_state:
            user_input = st.session_state.pop("quick_q")

        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)
            with st.chat_message("assistant"):
                with st.spinner("분석 중..."):
                    response = chat_with_analyst(api_key, user_input)
                st.write(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

        if st.session_state.chat_history:
            if st.button("대화 초기화"):
                st.session_state.chat_history = []
                st.rerun()
