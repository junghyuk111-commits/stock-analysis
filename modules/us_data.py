import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# 주요 미국 종목 기본 워치리스트
DEFAULT_US_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "AMD", "INTC", "AVGO", "ORCL", "CRM", "NFLX", "ADBE",
    "JPM", "BAC", "GS", "V", "MA", "PYPL",
    "SPY", "QQQ", "SOXS", "TQQQ"
]

# S&P500 급등주 스캔용 대형주 목록
SCAN_LIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    "AVGO", "ORCL", "CRM", "NFLX", "ADBE", "INTC", "QCOM",
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA",
    "XOM", "CVX", "LLY", "UNH", "JNJ", "PFE", "MRNA",
    "COST", "WMT", "TGT", "AMGN", "GILD", "BKNG", "UBER", "ABNB",
    "PLTR", "SOFI", "RIVN", "NIO", "LCID", "HOOD", "COIN",
    "SPY", "QQQ", "IWM", "DIA"
]


def get_hot_stocks_us(top_n=20):
    """미국 급등주: 당일 등락률/거래량 상위"""
    data = []
    tickers = yf.Tickers(" ".join(SCAN_LIST))

    for ticker_sym in SCAN_LIST:
        try:
            t = yf.Ticker(ticker_sym)
            info = t.fast_info
            hist = t.history(period="2d")
            if len(hist) < 2:
                continue

            today_close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change_pct = ((today_close - prev_close) / prev_close) * 100
            today_vol = hist['Volume'].iloc[-1]
            prev_vol = hist['Volume'].iloc[-2]
            vol_ratio = today_vol / max(prev_vol, 1)

            data.append({
                '티커': ticker_sym,
                '종목명': ticker_sym,
                '종가': round(today_close, 2),
                '전일종가': round(prev_close, 2),
                '등락률': round(change_pct, 2),
                '거래량': int(today_vol),
                '거래량비율': round(vol_ratio, 1),
                '시장': 'US',
            })
        except Exception:
            continue

    df = pd.DataFrame(data)
    if df.empty:
        return df

    hot = df[
        (df['등락률'] >= 2) &
        (df['거래량비율'] >= 1.3)
    ].sort_values(['등락률', '거래량비율'], ascending=False).head(top_n)

    return hot.reset_index(drop=True)


def get_us_stock_history(ticker, period="3mo"):
    """미국 종목 히스토리"""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period)
        return df
    except Exception as e:
        print(f"[US] 히스토리 오류 {ticker}: {e}")
        return pd.DataFrame()


def get_us_fundamentals(ticker):
    """미국 종목 재무 지표"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            'PER': info.get('trailingPE', 'N/A'),
            'Forward PER': info.get('forwardPE', 'N/A'),
            'PBR': info.get('priceToBook', 'N/A'),
            'EPS': info.get('trailingEps', 'N/A'),
            'ROE': info.get('returnOnEquity', 'N/A'),
            '시가총액': info.get('marketCap', 'N/A'),
            '배당수익률': info.get('dividendYield', 'N/A'),
            '52주 최고': info.get('fiftyTwoWeekHigh', 'N/A'),
            '52주 최저': info.get('fiftyTwoWeekLow', 'N/A'),
            '업종': info.get('sector', 'N/A'),
            '종목명': info.get('longName', ticker),
        }
    except Exception as e:
        print(f"[US] 재무지표 오류 {ticker}: {e}")
        return {}


def get_us_news(ticker, max_items=5):
    """Yahoo Finance 뉴스"""
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
        result = []
        for item in news[:max_items]:
            result.append({
                '제목': item.get('title', ''),
                '링크': item.get('link', ''),
                '시간': datetime.fromtimestamp(item.get('providerPublishTime', 0)).strftime('%Y-%m-%d %H:%M'),
            })
        return result
    except Exception:
        return []
