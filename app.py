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

# ── 페이지 설정 ────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 주식 분석 대시보드",
    page_icon="📈",
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

# ── 사이드바 ───────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 AI 주식 분석")
    st.caption(f"기준일: {get_last_trading_date()}")

    api_key = st.text_input(
        "Anthropic API Key",
        value=_secret("ANTHROPIC_API_KEY"),
        type="password",
        placeholder="sk-ant-...",
        help="AI 분석 기능에 필요. console.anthropic.com에서 발급"
    )
    if api_key:
        st.success("API 키 설정됨 ✅")
    else:
        st.info("API 키 없어도 스캐너 사용 가능")

    st.divider()
    market_filter = st.selectbox(
        "분석 시장",
        ["ALL (국내)", "KOSPI", "KOSDAQ", "미국"],
        index=0
    )
    top_n = st.slider("표시 종목 수", 10, 50, 20)

    st.divider()
    with st.expander("📧 이메일 리포트 설정"):
        gmail_addr = st.text_input("Gmail 주소", value=_secret("GMAIL_ADDRESS"),
                                   placeholder="you@gmail.com", key="gmail_addr")
        gmail_pw = st.text_input("앱 비밀번호", value=_secret("GMAIL_APP_PASSWORD"),
                                  type="password", key="gmail_pw",
                                  help="Gmail 앱 비밀번호 (일반 비밀번호 X)")
        recv_addr = st.text_input("수신 이메일", value=_secret("RECV_EMAIL"),
                                   placeholder="받을 주소", key="recv_addr")
        if gmail_addr and gmail_pw:
            st.success("이메일 설정됨 ✅")
        st.caption("[앱 비밀번호 발급 방법](https://myaccount.google.com/apppasswords)")

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
    "👀 거래량 이상",
    "📐 돌파 직전",
    "📉 저점 매수",
    "🔄 눌림목",
    "🚀 52주 신고가",
    "💡 AI 추천",
    "🔍 종목 분석",
    "💬 AI 챗",
])

tab_hot, tab_vol, tab_break, tab_over, tab_pull, tab_high, tab_ai, tab_stock, tab_chat = tabs


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
# TAB 2: 거래량 이상 감지
# ══════════════════════════════════════════════════════════════
with tab_vol:
    st.header("👀 거래량 이상 감지")
    st.markdown("""
    > **주가는 아직 조용한데 거래량이 평소의 2배 이상** — 세력 매집 가능성
    > 급등 전 가장 먼저 나타나는 신호. 관심 종목으로 등록해두고 지켜보기
    """)
    st.info("💡 **활용법:** 이 종목들을 매일 체크 → 주가까지 움직이기 시작하면 매수 고려")

    if run_button("거래량 이상 스캔", "run_vol"):
        with st.spinner("60일 데이터 분석 중... (30초 소요)"):
            st.session_state.vol_df = scan_volume_anomaly(get_market_code(), top_n)

    show_scanner_result(
        st.session_state.get("vol_df"),
        "20일 평균 대비 거래량 2배↑ & 주가 변동 3% 미만",
        "vol", "거래량비율(20일)"
    )


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
# TAB 4: 저점 매수 (역발상)
# ══════════════════════════════════════════════════════════════
with tab_over:
    st.header("📉 저점 매수 (역발상)")
    st.markdown("""
    > **RSI 38 이하** + **52주 저점 20% 이내** — 더 떨어지기 어려운 구간
    > 단, 추가 하락 가능성 있으므로 분할 매수 필수
    """)
    st.warning("⚠️ **주의:** 하락 추세 종목은 RSI가 낮아도 더 떨어질 수 있습니다. 재무가 괜찮은 종목만 고려하세요.")

    if run_button("저점 종목 스캔", "run_over"):
        with st.spinner("분석 중..."):
            st.session_state.over_df = scan_oversold(get_market_code(), top_n)

    show_scanner_result(
        st.session_state.get("over_df"),
        "RSI 38↓ & 52주 저점 20% 이내",
        "over", "RSI"
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
# TAB 6: 52주 신고가
# ══════════════════════════════════════════════════════════════
with tab_high:
    st.header("🚀 52주 신고가 돌파")
    st.markdown("""
    > 저항선이 모두 사라진 구간 — **이론상 위로 막히는 가격이 없음**
    > 모멘텀 투자의 핵심 신호
    """)
    st.info("💡 **활용법:** 신고가 돌파 + 거래량 폭발 시 추격 매수 / 단, 직후 눌림목에서 재진입이 더 안전")

    if run_button("신고가 스캔", "run_high"):
        with st.spinner("분석 중..."):
            st.session_state.high_df = scan_new_high(get_market_code(), top_n)

    show_scanner_result(
        st.session_state.get("high_df"),
        "52주 신고가 돌파 또는 1% 이내 접근",
        "high"
    )


# ══════════════════════════════════════════════════════════════
# TAB 7: AI 추천
# ══════════════════════════════════════════════════════════════
with tab_ai:
    st.header("💡 AI 오늘의 추천 종목")

    if not api_key:
        st.warning("사이드바에서 API 키를 입력해주세요.")
    else:
        col_btn, col_desc = st.columns([1, 4])
        with col_btn:
            run_ai = st.button("AI 분석 실행", type="primary", use_container_width=True)
        with col_desc:
            st.caption("급등주 + 거래량이상 + 돌파직전 데이터를 종합해 Claude AI가 오늘의 유망 종목을 선정합니다.")

        if run_ai:
            # 가용한 스캐너 결과 모두 취합
            all_data = {}
            for key, label in [("hot_df", "급등주"), ("vol_df", "거래량이상"),
                                ("break_df", "돌파직전"), ("pull_df", "눌림목")]:
                if key in st.session_state and not st.session_state[key].empty:
                    all_data[label] = st.session_state[key]

            if not all_data:
                st.warning("먼저 다른 탭에서 스캔을 실행해주세요.")
            else:
                summary_lines = []
                for label, df in all_data.items():
                    name_col = "종목명" if "종목명" in df.columns else "티커"
                    ticker_col = "티커" if "티커" in df.columns else name_col
                    for _, row in df.head(10).iterrows():
                        chg = row.get("등락률", "")
                        chg_str = f" 등락:{chg:.1f}%" if isinstance(chg, (int, float)) else ""
                        summary_lines.append(
                            f"[{label}] {row.get(name_col,'')}({row.get(ticker_col,'')}){chg_str}"
                        )

                market_news = get_naver_market_news(5)
                with st.spinner("Claude AI 분석 중... (15~20초)"):
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
                    with st.expander(
                        f"{pick.get('순위','')}위 | **{pick.get('종목명','')}** "
                        f"({pick.get('티커','')}) {emoji} {pick.get('전략','')} "
                        f"| 예상 {pick.get('예상수익률','')}",
                        expanded=True
                    ):
                        st.write(pick.get("추천이유", ""))

                # 이메일 발송 버튼
                st.divider()
                col_mail, col_info = st.columns([1, 3])
                with col_mail:
                    send_btn = st.button("📧 이메일로 받기", type="secondary", use_container_width=True)
                with col_info:
                    st.caption("사이드바 '이메일 리포트 설정'에서 Gmail 주소와 앱 비밀번호를 먼저 입력해주세요.")

                if send_btn:
                    g_addr = st.session_state.get("gmail_addr", "")
                    g_pw = st.session_state.get("gmail_pw", "")
                    r_addr = st.session_state.get("recv_addr", "") or g_addr
                    if not g_addr or not g_pw:
                        st.error("사이드바에서 Gmail 주소와 앱 비밀번호를 입력해주세요.")
                    else:
                        with st.spinner("이메일 발송 중..."):
                            html = build_report_html(picks)
                            ok, msg = send_daily_report(g_addr, g_pw, r_addr, html)
                        if ok:
                            st.success(f"✅ {r_addr} 로 리포트가 발송되었습니다!")
                        else:
                            st.error(f"❌ {msg}")


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
            if st.button("🤖 Claude AI 심층 분석", type="primary"):
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
