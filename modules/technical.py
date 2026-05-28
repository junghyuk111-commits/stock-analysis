import pandas as pd
import numpy as np


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).round(2)


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    histogram = macd - signal_line
    return macd.round(2), signal_line.round(2), histogram.round(2)


def calc_bollinger(series, period=20, std=2):
    ma = series.rolling(period).mean()
    upper = ma + std * series.rolling(period).std()
    lower = ma - std * series.rolling(period).std()
    return ma.round(2), upper.round(2), lower.round(2)


def get_indicators(df):
    """
    OHLCV DataFrame으로 주요 기술적 지표 계산
    컬럼: 종가(Close 또는 '종가'), 거래량(Volume 또는 '거래량')
    """
    close_col = 'Close' if 'Close' in df.columns else '종가'
    vol_col = 'Volume' if 'Volume' in df.columns else '거래량'

    if df.empty or len(df) < 30:
        return {}

    close = df[close_col].astype(float)
    volume = df[vol_col].astype(float) if vol_col in df.columns else None

    rsi = calc_rsi(close)
    macd, macd_signal, macd_hist = calc_macd(close)
    bb_ma, bb_upper, bb_lower = calc_bollinger(close)

    latest = close.iloc[-1]
    bb_pos = ((latest - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]) * 100).round(1)

    avg_vol_20 = volume.rolling(20).mean().iloc[-1] if volume is not None else None
    vol_ratio = (volume.iloc[-1] / avg_vol_20).round(1) if avg_vol_20 else None

    indicators = {
        'RSI': float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None,
        'MACD': float(macd.iloc[-1]) if not pd.isna(macd.iloc[-1]) else None,
        'MACD_Signal': float(macd_signal.iloc[-1]) if not pd.isna(macd_signal.iloc[-1]) else None,
        'MACD_Hist': float(macd_hist.iloc[-1]) if not pd.isna(macd_hist.iloc[-1]) else None,
        'BB_상단': float(bb_upper.iloc[-1]) if not pd.isna(bb_upper.iloc[-1]) else None,
        'BB_중간': float(bb_ma.iloc[-1]) if not pd.isna(bb_ma.iloc[-1]) else None,
        'BB_하단': float(bb_lower.iloc[-1]) if not pd.isna(bb_lower.iloc[-1]) else None,
        'BB_위치': float(bb_pos) if not pd.isna(bb_pos) else None,
        '거래량비율_20MA': float(vol_ratio) if vol_ratio and not pd.isna(vol_ratio) else None,
        '이동평균_5': float(close.rolling(5).mean().iloc[-1]),
        '이동평균_20': float(close.rolling(20).mean().iloc[-1]),
        '이동평균_60': float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else None,
    }
    return indicators


def interpret_signal(indicators):
    """지표 기반 매매 신호 해석"""
    signals = []
    score = 0  # 양수=매수, 음수=매도

    rsi = indicators.get('RSI')
    if rsi:
        if rsi < 30:
            signals.append(f"RSI {rsi:.0f} — 과매도 구간 (매수 신호)")
            score += 2
        elif rsi > 70:
            signals.append(f"RSI {rsi:.0f} — 과매수 구간 (매도 신호)")
            score -= 2
        else:
            signals.append(f"RSI {rsi:.0f} — 중립")

    macd_hist = indicators.get('MACD_Hist')
    macd = indicators.get('MACD')
    macd_sig = indicators.get('MACD_Signal')
    if macd and macd_sig:
        if macd > macd_sig and macd_hist and macd_hist > 0:
            signals.append("MACD 골든크로스 — 상승 모멘텀")
            score += 1
        elif macd < macd_sig:
            signals.append("MACD 데드크로스 — 하락 모멘텀")
            score -= 1

    bb_pos = indicators.get('BB_위치')
    if bb_pos is not None:
        if bb_pos < 20:
            signals.append(f"볼린저밴드 하단 근접 ({bb_pos:.0f}%) — 반등 가능성")
            score += 1
        elif bb_pos > 80:
            signals.append(f"볼린저밴드 상단 근접 ({bb_pos:.0f}%) — 과열 주의")
            score -= 1

    ma5 = indicators.get('이동평균_5')
    ma20 = indicators.get('이동평균_20')
    if ma5 and ma20:
        if ma5 > ma20:
            signals.append("5MA > 20MA — 단기 상승 추세")
            score += 1
        else:
            signals.append("5MA < 20MA — 단기 하락 추세")
            score -= 1

    if score >= 3:
        overall = "강한 매수"
    elif score >= 1:
        overall = "매수"
    elif score <= -3:
        overall = "강한 매도"
    elif score <= -1:
        overall = "매도"
    else:
        overall = "중립/관망"

    return overall, signals, score
