"""
하윤아빠의 추천종목 — 전략별 점수 기반 스마트 스캐너
단타 / 스윙 / 중장기 각각 다른 가중치로 종목 점수화
"""
import yfinance as yf
import pandas as pd
import numpy as np
from modules.krx_data import KOSPI_STOCKS, KOSDAQ_STOCKS, _ticker_yf
from modules.us_data import SCAN_LIST
from modules.technical import calc_rsi, calc_macd


def _get_all_stocks(market="ALL"):
    if market == "미국":
        return [(t, t, "US") for t in SCAN_LIST]
    stocks = []
    if market in ("ALL", "KOSPI"):
        stocks += [(t, n, "KOSPI") for t, n in KOSPI_STOCKS]
    if market in ("ALL", "KOSDAQ"):
        stocks += [(t, n, "KOSDAQ") for t, n in KOSDAQ_STOCKS]
    return stocks


def _score_daytrade(row):
    """단타 점수: 거래량 급증 + 모멘텀 + RSI"""
    score = 0

    # 거래량 급증 (30점)
    vr = row.get("거래량비율", 1)
    if vr >= 3: score += 30
    elif vr >= 2: score += 20
    elif vr >= 1.5: score += 10

    # 가격 모멘텀 (25점)
    chg = row.get("등락률", 0)
    if 2 <= chg <= 8: score += 25
    elif 1 <= chg < 2: score += 15
    elif 8 < chg <= 15: score += 10  # 너무 많이 오른 건 감점

    # RSI (20점) - 50~65가 이상적
    rsi = row.get("RSI", 50)
    if 50 <= rsi <= 65: score += 20
    elif 45 <= rsi < 50: score += 12
    elif 65 < rsi <= 75: score += 8

    # 골든크로스 (25점)
    if row.get("골든크로스", False): score += 25
    elif row.get("MA5_위_MA20", False): score += 10

    return min(score, 100)


def _score_swing(row):
    """스윙 점수: 기술적 셋업 + 재무 균형"""
    score = 0

    # 골든크로스 / 기술적 셋업 (30점)
    if row.get("골든크로스", False): score += 30
    elif row.get("MA5_위_MA20", False): score += 15

    # PER 저평가 (25점)
    per = row.get("PER", 999)
    if isinstance(per, (int, float)) and per > 0:
        if per < 10: score += 25
        elif per < 15: score += 18
        elif per < 20: score += 10
        elif per < 25: score += 5

    # 가격 모멘텀 (20점)
    chg = row.get("등락률", 0)
    if 1 <= chg <= 5: score += 20
    elif 0 <= chg < 1: score += 10

    # RSI (15점) - 45~60
    rsi = row.get("RSI", 50)
    if 45 <= rsi <= 60: score += 15
    elif 40 <= rsi < 45: score += 8

    # 거래량 (10점)
    vr = row.get("거래량비율", 1)
    if vr >= 1.5: score += 10
    elif vr >= 1.2: score += 5

    return min(score, 100)


def _score_longterm(row):
    """중장기 점수: 재무 퀄리티 최우선"""
    score = 0

    # PER 저평가 (30점)
    per = row.get("PER", 999)
    if isinstance(per, (int, float)) and per > 0:
        if per < 8: score += 30
        elif per < 12: score += 22
        elif per < 17: score += 12
        elif per < 22: score += 5

    # ROE (35점)
    roe = row.get("ROE", 0)
    if isinstance(roe, (int, float)):
        if roe > 20: score += 35
        elif roe > 15: score += 25
        elif roe > 10: score += 15
        elif roe > 5: score += 5

    # RSI (15점) - 40~55 저평가 구간
    rsi = row.get("RSI", 50)
    if 40 <= rsi <= 55: score += 15
    elif 35 <= rsi < 40: score += 10
    elif 55 < rsi <= 65: score += 8

    # MA 추세 (10점)
    if row.get("MA5_위_MA20", False): score += 10

    # 가격 모멘텀 (10점) - 완만한 상승
    chg = row.get("등락률", 0)
    if 0.5 <= chg <= 3: score += 10
    elif 0 <= chg < 0.5: score += 5

    return min(score, 100)


def scan_smart_picks(market="ALL", top_n=5):
    """
    전략별 점수 산출 후 상위 종목 반환
    returns: dict with keys '단타', '스윙', '중장기'
    """
    stocks = _get_all_stocks(market)
    tickers_yf = [_ticker_yf(t, m) if m != "US" else t for t, n, m in stocks]
    ticker_meta = {
        (_ticker_yf(t, m) if m != "US" else t): (t, n, m)
        for t, n, m in stocks
    }
    currency = "$" if market == "미국" else "원"

    try:
        data = yf.download(tickers_yf, period="60d", auto_adjust=True, progress=False)
    except Exception as e:
        return {"오류": str(e)}

    if isinstance(data.columns, pd.MultiIndex):
        close_all = data["Close"]
        volume_all = data["Volume"]
    else:
        return {"오류": "데이터 없음"}

    rows = []
    for yf_t in tickers_yf:
        try:
            if yf_t not in close_all.columns:
                continue
            c = close_all[yf_t].dropna()
            v = volume_all[yf_t].dropna() if yf_t in volume_all.columns else pd.Series()
            if len(c) < 25:
                continue

            today_close = float(c.iloc[-1])
            prev_close = float(c.iloc[-2])
            change_pct = (today_close - prev_close) / prev_close * 100

            today_vol = float(v.iloc[-1]) if len(v) > 0 else 0
            avg_vol_20 = float(v.iloc[-21:-1].mean()) if len(v) > 21 else 1
            vol_ratio = today_vol / max(avg_vol_20, 1)

            rsi_series = calc_rsi(c)
            rsi_now = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50

            ma5 = float(c.rolling(5).mean().iloc[-1])
            ma20 = float(c.rolling(20).mean().iloc[-1])
            ma5_prev = float(c.rolling(5).mean().iloc[-2])
            ma20_prev = float(c.rolling(20).mean().iloc[-2])
            golden_cross = (ma5_prev < ma20_prev) and (ma5 >= ma20)
            above_ma20 = ma5 > ma20

            # 펀더멘털 (가능한 경우)
            per, roe = None, None
            try:
                info = yf.Ticker(yf_t).fast_info
                per = getattr(info, 'pe_ratio', None)
            except Exception:
                pass

            org_ticker, name, mkt = ticker_meta[yf_t]
            rows.append({
                "티커": org_ticker,
                "종목명": name,
                "시장": mkt,
                "현재가": round(today_close, 2),
                "통화": currency,
                "등락률": round(change_pct, 2),
                "거래량비율": round(vol_ratio, 1),
                "RSI": round(rsi_now, 1),
                "MA5": round(ma5, 0),
                "MA20": round(ma20, 0),
                "골든크로스": golden_cross,
                "MA5_위_MA20": above_ma20,
                "PER": round(per, 1) if per and per > 0 else "N/A",
                "ROE": roe or 0,
            })
        except Exception:
            continue

    if not rows:
        return {"단타": pd.DataFrame(), "스윙": pd.DataFrame(), "중장기": pd.DataFrame()}

    df = pd.DataFrame(rows)
    df["단타점수"] = df.apply(_score_daytrade, axis=1)
    df["스윙점수"] = df.apply(_score_swing, axis=1)
    df["중장기점수"] = df.apply(_score_longterm, axis=1)

    result = {}
    for strategy, col in [("단타", "단타점수"), ("스윙", "스윙점수"), ("중장기", "중장기점수")]:
        top = df[df[col] >= 50].sort_values(col, ascending=False).head(top_n).copy()
        top = top.rename(columns={col: "점수"})
        result[strategy] = top.reset_index(drop=True)

    return result


def build_smart_summary(picks_dict, currency="원"):
    """Claude에게 넘길 요약 텍스트 생성"""
    lines = []
    for strategy, df in picks_dict.items():
        if df is None or df.empty:
            continue
        for _, row in df.head(8).iterrows():
            per_str = f" PER:{row.get('PER','N/A')}" if row.get('PER') != 'N/A' else ""
            lines.append(
                f"[{strategy}후보] {row.get('종목명','')}({row.get('티커','')}) "
                f"현재가:{row.get('현재가',0):,.0f}{currency} "
                f"점수:{row.get('점수',0):.0f}점 "
                f"등락:{row.get('등락률',0):+.1f}% "
                f"RSI:{row.get('RSI',0):.0f} "
                f"거래량:{row.get('거래량비율',0):.1f}x"
                f"{per_str}"
            )
    return "\n".join(lines)
