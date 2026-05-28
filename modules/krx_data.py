"""
한국 주식 데이터 - yfinance 기반 (.KS = KOSPI, .KQ = KOSDAQ)
"""
import yfinance as yf
import pandas as pd
from datetime import datetime

# 주요 KOSPI 종목 (티커, 종목명, 시장)
KOSPI_STOCKS = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
    ("207940", "삼성바이오로직스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("051910", "LG화학"), ("035420", "NAVER"),
    ("005490", "POSCO홀딩스"), ("035720", "카카오"), ("000810", "삼성화재"),
    ("012330", "현대모비스"), ("105560", "KB금융"), ("055550", "신한지주"),
    ("086790", "하나금융지주"), ("316140", "우리금융지주"), ("024110", "기업은행"),
    ("009150", "삼성전기"), ("028260", "삼성물산"), ("017670", "SK텔레콤"),
    ("030200", "KT"), ("032830", "삼성생명"), ("066570", "LG전자"),
    ("034730", "SK"), ("096770", "SK이노베이션"), ("011200", "HMM"),
    ("003550", "LG"), ("010950", "S-Oil"), ("015760", "한국전력"),
]

# 주요 KOSDAQ 종목
KOSDAQ_STOCKS = [
    ("247540", "에코프로비엠"), ("086520", "에코프로"), ("003230", "삼양식품"),
    ("196170", "알테오젠"), ("263750", "펄어비스"), ("293490", "카카오게임즈"),
    ("112040", "위메이드"), ("041510", "에스엠"), ("352820", "하이브"),
    ("035900", "JYP엔터"), ("122870", "와이지엔터테인먼트"), ("145720", "덴티움"),
    ("091990", "셀트리온헬스케어"), ("005290", "동진쎄미켐"), ("064760", "티씨케이"),
    ("039030", "이오테크닉스"), ("036670", "파라다이스"), ("357780", "솔브레인"),
    ("240810", "원익IPS"), ("131970", "두산테스나"),
]


def _ticker_yf(ticker, market="KOSPI"):
    suffix = ".KS" if market == "KOSPI" else ".KQ"
    return ticker + suffix


def get_hot_stocks_krx(market="ALL", top_n=30):
    """급등주 스캔 (yfinance 기반)"""
    stocks = []
    if market in ("ALL", "KOSPI"):
        stocks += [(t, n, "KOSPI") for t, n in KOSPI_STOCKS]
    if market in ("ALL", "KOSDAQ"):
        stocks += [(t, n, "KOSDAQ") for t, n in KOSDAQ_STOCKS]

    results = []
    tickers_yf = [_ticker_yf(t, m) for t, n, m in stocks]
    ticker_meta = {_ticker_yf(t, m): (t, n, m) for t, n, m in stocks}

    try:
        data = yf.download(tickers_yf, period="5d", auto_adjust=True, progress=False)
    except Exception as e:
        print(f"[KRX] 다운로드 오류: {e}")
        return pd.DataFrame()

    # MultiIndex 처리
    if isinstance(data.columns, pd.MultiIndex):
        close = data['Close'] if 'Close' in data.columns.get_level_values(0) else pd.DataFrame()
        volume = data['Volume'] if 'Volume' in data.columns.get_level_values(0) else pd.DataFrame()
    else:
        close = data[['Close']] if 'Close' in data.columns else pd.DataFrame()
        volume = data[['Volume']] if 'Volume' in data.columns else pd.DataFrame()

    if close.empty or len(close) < 2:
        return pd.DataFrame()

    for yf_ticker in tickers_yf:
        try:
            if yf_ticker not in close.columns:
                continue
            c = close[yf_ticker].dropna()
            v = volume[yf_ticker].dropna() if yf_ticker in volume.columns else None
            if len(c) < 2:
                continue

            today_close = float(c.iloc[-1])
            prev_close = float(c.iloc[-2])
            change_pct = (today_close - prev_close) / prev_close * 100

            today_vol = int(v.iloc[-1]) if v is not None and len(v) >= 2 else 0
            prev_vol = int(v.iloc[-2]) if v is not None and len(v) >= 2 else 1
            vol_ratio = today_vol / max(prev_vol, 1)

            org_ticker, name, mkt = ticker_meta[yf_ticker]
            results.append({
                '티커': org_ticker,
                '종목명': name,
                '시장': mkt,
                '종가': today_close,
                '전일종가': prev_close,
                '등락률': round(change_pct, 2),
                '거래량': today_vol,
                '거래량비율': round(vol_ratio, 1),
            })
        except Exception:
            continue

    df = pd.DataFrame(results)
    if df.empty:
        return df

    hot = df[
        (df['등락률'] >= 1)  # 1% 이상 상승
    ].sort_values(['등락률', '거래량비율'], ascending=False).head(top_n)

    return hot.reset_index(drop=True)


def get_stock_history(ticker, market="KOSPI", days=90):
    """종목 가격 히스토리"""
    yf_ticker = _ticker_yf(ticker, market)
    period = f"{days}d" if days <= 60 else "3mo"
    try:
        df = yf.download(yf_ticker, period=period, auto_adjust=True, progress=False)
        return df
    except Exception as e:
        print(f"[KRX] 히스토리 오류 {ticker}: {e}")
        return pd.DataFrame()


def get_fundamentals(ticker, market="KOSPI"):
    """재무 지표"""
    yf_ticker = _ticker_yf(ticker, market)
    try:
        t = yf.Ticker(yf_ticker)
        info = t.info
        return {
            'PER': info.get('trailingPE', 'N/A'),
            'Forward PER': info.get('forwardPE', 'N/A'),
            'PBR': info.get('priceToBook', 'N/A'),
            'EPS': info.get('trailingEps', 'N/A'),
            'ROE': round(info.get('returnOnEquity', 0) * 100, 1) if info.get('returnOnEquity') else 'N/A',
            '시가총액(억)': round(info.get('marketCap', 0) / 1e8, 0) if info.get('marketCap') else 'N/A',
            '배당수익률': round(info.get('dividendYield', 0) * 100, 2) if info.get('dividendYield') else 'N/A',
            '52주최고': info.get('fiftyTwoWeekHigh', 'N/A'),
            '52주최저': info.get('fiftyTwoWeekLow', 'N/A'),
        }
    except Exception as e:
        print(f"[KRX] 재무지표 오류 {ticker}: {e}")
        return {}


def search_krx_ticker(query):
    """종목명 또는 티커로 검색"""
    results = []
    all_stocks = [(t, n, "KOSPI") for t, n in KOSPI_STOCKS] + \
                 [(t, n, "KOSDAQ") for t, n in KOSDAQ_STOCKS]
    query_upper = query.upper()
    for ticker, name, market in all_stocks:
        if query_upper in ticker or query in name:
            results.append({'티커': ticker, '종목명': name, '시장': market})
    return results


def get_last_trading_date():
    """참고용 날짜 (영업일 기준)"""
    from datetime import timedelta
    today = datetime.now()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    return today.strftime('%Y%m%d')
