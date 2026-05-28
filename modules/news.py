import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re


def get_naver_stock_news(ticker, max_items=5):
    """네이버 금융 종목 뉴스 스크래핑"""
    url = f"https://finance.naver.com/item/news_news.nhn?code={ticker}&page=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com'
    }
    news_list = []
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'lxml')
        rows = soup.select('table.type5 tr')
        for row in rows:
            title_tag = row.select_one('td.title a')
            date_tag = row.select_one('td.date')
            if title_tag and date_tag:
                news_list.append({
                    '제목': title_tag.get_text(strip=True),
                    '링크': 'https://finance.naver.com' + title_tag.get('href', ''),
                    '시간': date_tag.get_text(strip=True),
                })
            if len(news_list) >= max_items:
                break
    except Exception as e:
        print(f"[NEWS] 네이버 뉴스 오류 {ticker}: {e}")
    return news_list


def get_naver_market_news(max_items=10):
    """네이버 금융 시장 전체 뉴스"""
    url = "https://finance.naver.com/news/mainnews.nhn"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    news_list = []
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'lxml')
        items = soup.select('ul.newsList li')
        for item in items[:max_items]:
            title_tag = item.select_one('dd.articleSubject a')
            date_tag = item.select_one('span.wdate')
            if title_tag:
                news_list.append({
                    '제목': title_tag.get_text(strip=True),
                    '링크': 'https://finance.naver.com' + title_tag.get('href', ''),
                    '시간': date_tag.get_text(strip=True) if date_tag else '',
                })
    except Exception as e:
        print(f"[NEWS] 시장 뉴스 오류: {e}")
    return news_list


def format_news_for_prompt(news_list):
    """Claude 프롬프트용 뉴스 텍스트 변환"""
    if not news_list:
        return "관련 뉴스 없음"
    lines = []
    for i, n in enumerate(news_list, 1):
        lines.append(f"{i}. [{n.get('시간', '')}] {n.get('제목', '')}")
    return "\n".join(lines)
