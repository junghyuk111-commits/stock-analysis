"""
다양한 매매 신호 스캐너
"""
import yfinance as yf
import pandas as pd
import numpy as np
from modules.krx_data import KOSPI_STOCKS, KOSDAQ_STOCKS, _ticker_yf
from modules.us_data import SCAN_LIST
from modules.technical import calc_rsi, calc_macd


def _load_all_history(market="ALL", period="60d"):
    """전 종목 히스토리 일괄 다운로드"""
    if market == "미국":
        tickers_yf = SCAN_LIST
        meta = {t: (t, t, "US") for t in SCAN_LIST}
    else:
        stocks = []
        if market in ("ALL", "KOSPI"):
            stocks += [(t, n, "KOSPI") for t, n in KOSPI_STOCKS]
        if market in ("ALL", "KOSDAQ"):
            stocks += [(t, n, "KOSDAQ") for t, n in KOSDAQ_STOCKS]
        tickers_yf = [_ticker_yf(t, m) for t, n, m in stocks]
        meta = {_ticker_yf(t, m): (t, n, m) for t, n, m in stocks}

    try:
        data = yf.download(tickers_yf, period=period, auto_adjust=True, progress=False)
    except Exception as e:
        print(f"[SCANNER] 다운로드 오류: {e}")
        return {}, meta

    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"]
        volume = data["Volume"]
        high = data["High"]
        low = data["Low"]
    else:
        close = data[["Close"]]
        volume = data[["Volume"]]
        high = data[["High"]]
        low = data[["Low"]]

    result = {}
    for yf_t in tickers_yf:
        if yf_t not in close.columns:
            continue
        c = close[yf_t].dropna()
        v = volume[yf_t].dropna() if yf_t in volume.columns else pd.Series()
        h = high[yf_t].dropna() if yf_t in high.columns else pd.Series()
        l = low[yf_t].dropna() if yf_t in low.columns else pd.Series()
        if len(c) < 20:
            continue
        result[yf_t] = {"close": c, "volume": v, "high": h, "low": l}

    return result, meta


# ── 1. 거래량 이상 감지 ─────────────────────────────────────────
def scan_volume_anomaly(market="ALL", top_n=20):
    """
    주가는 조용한데 거래량이 평소보다 갑자기 늘기 시작한 종목
    → 세력 매집 가능성, 급등 전 조용한 신호
    """
    data, meta = _load_all_history(market, period="60d")
    results = []

    for yf_t, d in data.items():
        c, v = d["close"], d["volume"]
        if len(v) < 21:
            continue
        avg_vol_20 = float(v.iloc[-21:-1].mean())
        if avg_vol_20 == 0:
            continue
        today_vol = float(v.iloc[-1])
        vol_ratio = today_vol / avg_vol_20

        today_close = float(c.iloc[-1])
        prev_close = float(c.iloc[-2])
        change_pct = (today_close - prev_close) / prev_close * 100

        # 핵심: 거래량 2배↑ 이면서 주가 변동은 3% 미만 (아직 안 터짐)
        if vol_ratio >= 2.0 and abs(change_pct) < 3:
            ticker, name, mkt = meta[yf_t]
            # 최근 5일 평균 거래량도 체크
            avg_vol_5 = float(v.iloc[-6:-1].mean())
            vol_trend = avg_vol_5 / avg_vol_20  # 5일 평균이 20일 평균보다 높으면 추세적

            results.append({
                "티커": ticker,
                "종목명": name,
                "시장": mkt,
                "현재가": round(today_close, 2),
                "등락률": round(change_pct, 2),
                "거래량비율(20일)": round(vol_ratio, 1),
                "거래량추세(5/20)": round(vol_trend, 2),
                "포인트": "거래량 급증 / 주가 아직 조용",
            })

    df = pd.DataFrame(results)
    if df.empty:
        return df
    return df.sort_values("거래량비율(20일)", ascending=False).head(top_n).reset_index(drop=True)


# ── 2. 돌파 직전 ───────────────────────────────────────────────
def scan_breakout_imminent(market="ALL", top_n=20):
    """
    52주 신고가 5% 이내 접근 OR MA5가 MA20 골든크로스 직전/직후
    → 추세 전환 + 모멘텀 발생 초입
    """
    data, meta = _load_all_history(market, period="60d")
    results = []

    for yf_t, d in data.items():
        c, v, h = d["close"], d["volume"], d["high"]
        if len(c) < 25:
            continue

        today_close = float(c.iloc[-1])
        high_52w = float(h.max()) if len(h) > 0 else today_close
        distance_to_high = (high_52w - today_close) / high_52w * 100

        ma5 = c.rolling(5).mean()
        ma20 = c.rolling(20).mean()
        ma5_now = float(ma5.iloc[-1])
        ma20_now = float(ma20.iloc[-1])
        ma5_prev = float(ma5.iloc[-2])
        ma20_prev = float(ma20.iloc[-2])

        # 골든크로스: 어제는 5<20 이었는데 오늘 5>20
        golden_cross = (ma5_prev < ma20_prev) and (ma5_now >= ma20_now)
        # 이미 골든크로스 후 3일 이내 (상승 초입)
        golden_recent = (ma5_now > ma20_now) and ((ma5_now - ma20_now) / ma20_now * 100 < 3)

        # RSI 50 회복
        rsi = calc_rsi(c)
        rsi_now = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

        signals = []
        score = 0
        if distance_to_high < 5:
            signals.append(f"52주 고점 {distance_to_high:.1f}% 이내")
            score += 2
        if golden_cross:
            signals.append("골든크로스 발생!")
            score += 3
        elif golden_recent:
            signals.append("골든크로스 후 상승 초입")
            score += 2
        if 48 < rsi_now < 60:
            signals.append(f"RSI {rsi_now:.0f} — 중립→강세 전환")
            score += 1

        if score >= 2:
            ticker, name, mkt = meta[yf_t]
            results.append({
                "티커": ticker,
                "종목명": name,
                "시장": mkt,
                "현재가": round(today_close, 2),
                "52주고점거리": f"-{distance_to_high:.1f}%",
                "MA5": round(ma5_now, 0),
                "MA20": round(ma20_now, 0),
                "RSI": round(rsi_now, 1),
                "신호": " / ".join(signals),
                "점수": score,
            })

    df = pd.DataFrame(results)
    if df.empty:
        return df
    return df.sort_values("점수", ascending=False).head(top_n).reset_index(drop=True)


# ── 3. 저점 매수 (과매도 역발상) ──────────────────────────────
def scan_oversold(market="ALL", top_n=20):
    """
    RSI 과매도 + 52주 저점 근처에서 버티는 종목
    → 더 떨어지기 어려운 구간, 반등 가능성
    """
    data, meta = _load_all_history(market, period="60d")
    results = []

    for yf_t, d in data.items():
        c, v, h, l = d["close"], d["volume"], d["high"], d["low"]
        if len(c) < 20:
            continue

        today_close = float(c.iloc[-1])
        low_52w = float(l.min()) if len(l) > 0 else today_close
        high_52w = float(h.max()) if len(h) > 0 else today_close
        distance_from_low = (today_close - low_52w) / low_52w * 100

        rsi = calc_rsi(c)
        rsi_now = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
        rsi_prev = float(rsi.iloc[-2]) if len(rsi) > 1 and not pd.isna(rsi.iloc[-2]) else rsi_now

        # 낙폭
        change_5d = (today_close - float(c.iloc[-6])) / float(c.iloc[-6]) * 100 if len(c) >= 6 else 0
        change_20d = (today_close - float(c.iloc[-21])) / float(c.iloc[-21]) * 100 if len(c) >= 21 else 0

        # 핵심: RSI 35 이하 + 52주 저점 15% 이내 + RSI가 바닥 찍고 반등 조짐
        if rsi_now <= 38 and distance_from_low <= 20:
            rsi_rebounding = rsi_now > rsi_prev  # RSI 반등 시작

            ticker, name, mkt = meta[yf_t]
            results.append({
                "티커": ticker,
                "종목명": name,
                "시장": mkt,
                "현재가": round(today_close, 2),
                "RSI": round(rsi_now, 1),
                "52주저점거리": f"+{distance_from_low:.1f}%",
                "5일등락": f"{change_5d:+.1f}%",
                "20일등락": f"{change_20d:+.1f}%",
                "RSI반등": "✅" if rsi_rebounding else "⏳",
                "포인트": "과매도 구간 진입" + (" + RSI 반등 시작" if rsi_rebounding else ""),
            })

    df = pd.DataFrame(results)
    if df.empty:
        return df
    return df.sort_values("RSI").head(top_n).reset_index(drop=True)


# ── 4. 눌림목 (급등 후 조정) ──────────────────────────────────
def scan_pullback(market="ALL", top_n=20):
    """
    최근 5~20일 내 강하게 올랐다가 지금 눌림목 중인 종목
    → 추세는 살아있고 잠깐 쉬는 구간 = 2차 매수 기회
    """
    data, meta = _load_all_history(market, period="60d")
    results = []

    for yf_t, d in data.items():
        c, v = d["close"], d["volume"]
        if len(c) < 25:
            continue

        today_close = float(c.iloc[-1])

        # 20일 전 대비 상승폭 (추세 확인)
        base_price = float(c.iloc[-21])
        trend_gain = (today_close - base_price) / base_price * 100

        # 고점 찾기 (최근 20일 중 최고가)
        recent_high = float(c.iloc[-20:].max())
        high_date_idx = c.iloc[-20:].argmax()
        pullback_pct = (today_close - recent_high) / recent_high * 100  # 음수

        # 현재 거래량이 평균보다 낮은지 (건강한 눌림목 = 거래량 감소)
        avg_vol = float(v.iloc[-21:-1].mean()) if len(v) > 21 else float(v.mean())
        today_vol = float(v.iloc[-1])
        vol_quiet = today_vol < avg_vol * 0.8

        # MA20 위에서 눌림목인지 (MA20이 지지선 역할)
        ma20 = c.rolling(20).mean()
        above_ma20 = today_close > float(ma20.iloc[-1])

        # RSI
        rsi = calc_rsi(c)
        rsi_now = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

        # 조건: 20일 추세 +5%↑, 고점 대비 -3~-15% 조정, MA20 위
        if trend_gain >= 5 and -15 <= pullback_pct <= -3 and above_ma20:
            ticker, name, mkt = meta[yf_t]
            results.append({
                "티커": ticker,
                "종목명": name,
                "시장": mkt,
                "현재가": round(today_close, 2),
                "20일추세": f"+{trend_gain:.1f}%",
                "고점대비조정": f"{pullback_pct:.1f}%",
                "MA20": round(float(ma20.iloc[-1]), 0),
                "RSI": round(rsi_now, 1),
                "거래량조용": "✅" if vol_quiet else "—",
                "포인트": f"추세 유지 + 눌림목 {pullback_pct:.0f}%",
            })

    df = pd.DataFrame(results)
    if df.empty:
        return df
    return df.sort_values("고점대비조정", ascending=False).head(top_n).reset_index(drop=True)


# ── 5. 52주 신고가 돌파 ────────────────────────────────────────
def scan_new_high(market="ALL", top_n=20):
    """
    52주 신고가를 막 돌파한 종목
    → 저항선이 사라지고 추세 가속 가능성
    """
    data, meta = _load_all_history(market, period="60d")
    results = []

    for yf_t, d in data.items():
        c, h = d["close"], d["high"]
        if len(c) < 50:
            continue

        today_close = float(c.iloc[-1])
        today_high = float(h.iloc[-1]) if len(h) > 0 else today_close

        # 52주 고점 (오늘 제외)
        prev_52w_high = float(h.iloc[:-1].max()) if len(h) > 1 else today_high

        # 오늘 종가 또는 고가가 이전 52주 고점 돌파
        breakout = today_close >= prev_52w_high * 0.99  # 1% 이내면 돌파 근접으로 포함

        if breakout:
            change_pct = (today_close - float(c.iloc[-2])) / float(c.iloc[-2]) * 100
            rsi = calc_rsi(c)
            rsi_now = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

            ticker, name, mkt = meta[yf_t]
            results.append({
                "티커": ticker,
                "종목명": name,
                "시장": mkt,
                "현재가": round(today_close, 2),
                "등락률": f"{change_pct:+.2f}%",
                "52주고점": round(prev_52w_high, 2),
                "돌파여부": "🚀 돌파" if today_close >= prev_52w_high else "⚡ 근접",
                "RSI": round(rsi_now, 1),
            })

    df = pd.DataFrame(results)
    if df.empty:
        return df
    return df.sort_values("현재가", ascending=False).head(top_n).reset_index(drop=True)
