import anthropic
import json
import re


SYSTEM_PROMPT = """당신은 10년 경력의 전문 주식 애널리스트입니다.
주어진 데이터를 바탕으로 냉정하고 객관적인 투자 분석을 제공합니다.
항상 JSON 형식으로만 응답하고, 투자 손실 가능성도 명확히 언급하세요."""


def analyze_single_stock(api_key, stock_info):
    """
    단일 종목 Claude AI 분석
    stock_info: dict with keys: 종목명, 시장, 현재가, 등락률, 거래량비율,
                                기술적지표, 재무지표, 뉴스, 통화
    """
    client = anthropic.Anthropic(api_key=api_key)

    통화 = stock_info.get('통화', '원')
    현재가 = stock_info.get('현재가', 0)
    종목명 = stock_info.get('종목명', '')

    indicators = stock_info.get('기술적지표', {})
    fundamentals = stock_info.get('재무지표', {})
    news_text = stock_info.get('뉴스', '없음')

    indicators_text = "\n".join([f"  - {k}: {v}" for k, v in indicators.items() if v is not None])
    fundamentals_text = "\n".join([f"  - {k}: {v}" for k, v in fundamentals.items()])

    prompt = f"""다음 종목을 분석해주세요.

## 종목 정보
- 종목명: {종목명}
- 시장: {stock_info.get('시장', '')}
- 현재가: {현재가:,}{통화}
- 당일 등락률: {stock_info.get('등락률', 0):.2f}%
- 거래량 (20일 평균 대비): {stock_info.get('거래량비율', 1):.1f}배

## 기술적 지표
{indicators_text}

## 재무 지표
{fundamentals_text}

## 최근 뉴스
{news_text}

아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "투자의견": "매수|관망|매도 중 하나",
  "신뢰도": "높음|보통|낮음 중 하나",
  "매수목표가": {현재가 * 0.97:.0f},
  "목표주가": {현재가 * 1.15:.0f},
  "손절가": {현재가 * 0.93:.0f},
  "단기전망": "1-2줄 단기(1-2주) 전망",
  "중기전망": "1-2줄 중기(1-3개월) 전망",
  "매수근거": ["근거1", "근거2", "근거3"],
  "리스크요인": ["리스크1", "리스크2"],
  "한줄요약": "핵심 한 줄 요약"
}}

매수목표가/목표주가/손절가는 실제 분석 기반으로 계산해서 숫자만 입력하세요."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text.strip()
        # JSON 파싱
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)
    except json.JSONDecodeError:
        return {"오류": "JSON 파싱 실패", "원문": text[:500]}
    except Exception as e:
        return {"오류": str(e)}


def get_daily_top_picks(api_key, hot_stocks_summary, market_news=""):
    """
    오늘의 추천 종목 top 5 선정 (급등주 목록 기반)
    """
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""오늘 주식시장 데이터입니다. 투자 유망 종목을 선정해주세요.

## 급등주 목록
{hot_stocks_summary}

## 시장 뉴스
{market_news if market_news else '없음'}

아래 JSON 형식으로만 응답하세요:
{{
  "시장요약": "오늘 시장 전반적 분위기 2줄",
  "추천종목": [
    {{
      "순위": 1,
      "종목명": "종목명",
      "티커": "티커",
      "추천이유": "2줄 이내",
      "전략": "단타|스윙|중장기 중 하나",
      "예상수익률": "X%"
    }}
  ],
  "오늘주의사항": "오늘 투자 시 주의할 점 1줄"
}}

추천종목은 최대 5개, 근거가 확실한 것만 포함하세요."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)
    except Exception as e:
        return {"오류": str(e)}


def chat_with_analyst(api_key, question, context=""):
    """자유 질문 애널리스트 챗"""
    client = anthropic.Anthropic(api_key=api_key)

    messages = []
    if context:
        messages.append({
            "role": "user",
            "content": f"참고 데이터:\n{context}\n\n질문: {question}"
        })
    else:
        messages.append({"role": "user", "content": question})

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system="당신은 전문 주식 애널리스트입니다. 한국어로 명확하고 실용적인 답변을 제공하세요. 투자는 본인 책임임을 항상 언급하세요.",
            messages=messages
        )
        return message.content[0].text
    except Exception as e:
        return f"오류: {e}"
