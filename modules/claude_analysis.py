import anthropic
import json
import re


def _parse_json_safe(text):
    """Claude 응답에서 JSON을 최대한 안전하게 파싱"""
    # 1차: 그대로 파싱
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2차: ```json ... ``` 블록 추출
    code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except Exception:
            pass

    # 3차: 첫 { 부터 마지막 } 까지 추출
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass

    # 4차: 줄바꿈 내 특수문자 제거 후 재시도
    try:
        cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', text[start:end+1])
        return json.loads(cleaned)
    except Exception:
        pass

    return {"오류": "AI 응답 파싱 실패 — 다시 시도해주세요", "원문": text[:300]}


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
        return _parse_json_safe(text)
    except json.JSONDecodeError:
        return {"오류": "JSON 파싱 실패", "원문": text[:500]}
    except Exception as e:
        return {"오류": str(e)}


def get_daily_top_picks(api_key, hot_stocks_summary, market_news=""):
    """오늘의 추천 종목 top 5 선정"""
    client = anthropic.Anthropic(api_key=api_key)

    system = """당신은 전문 주식 애널리스트입니다. 반드시 유효한 JSON만 출력하세요.
JSON 외 다른 텍스트, 마크다운 코드블록, 설명을 절대 포함하지 마세요.
문자열 안에 줄바꿈이 필요하면 \\n을 사용하세요."""

    rules = """진입 전략 규칙:
- 급등주: 매수가 = 현재가 x 0.95 (내일 눌림목 대기), 진입방법 = 눌림목대기
- 거래량이상: 매수가 = 현재가 x 0.99, 진입방법 = 지금바로
- 돌파직전: 매수가 = 현재가 x 0.99, 진입방법 = 지금바로
- 눌림목: 매수가 = 현재가 x 0.98, 진입방법 = 분할매수
목표가 = 매수가 x 1.07~1.15, 손절가 = 매수가 x 0.93~0.96"""

    prompt = f"""스캔 결과:
{hot_stocks_summary}

뉴스: {market_news or '없음'}

{rules}

위 현재가 기준으로 계산하여 아래 JSON을 출력하세요:
{{"시장요약":"string","추천종목":[{{"순위":1,"종목명":"string","티커":"string","전략":"단타또는스윙또는중장기","진입방법":"지금바로또는눌림목대기또는분할매수","매수가":"string","목표가":"string","손절가":"string","예상수익률":"string","추천이유":"string","주의사항":"string"}}],"오늘주의사항":"string"}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text.strip()
        return _parse_json_safe(text)
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


def get_smart_picks_analysis(api_key, summary, market_news=""):
    """
    전략별 점수 기반 후보군을 Claude가 심층 분석
    단타/스윙/중장기 각 2개씩 최종 추천
    """
    client = anthropic.Anthropic(api_key=api_key)

    system = """당신은 10년 경력 전문 주식 애널리스트입니다.
반드시 유효한 JSON만 출력하세요. 마크다운, 코드블록, 설명 절대 금지.
문자열 안 줄바꿈은 \\n 사용."""

    prompt = f"""다음은 전략별 점수로 필터링된 종목 후보입니다.
각 전략에서 최종 2개씩 선정하고 투자 근거를 제시하세요.

## 후보 종목 (점수 높을수록 해당 전략에 적합)
{summary}

## 시장 뉴스
{market_news or '없음'}

## 전략별 진입 방법
- 단타: 당일 또는 내일 장 초반 진입. 매수가=현재가×0.99, 목표가=매수가×1.04, 손절=매수가×0.97
- 스윙: 1~3주 보유. 매수가=현재가×0.98, 목표가=매수가×1.10, 손절=매수가×0.95
- 중장기: 1~3개월 보유. 분할매수. 매수가=현재가×0.97, 목표가=매수가×1.20, 손절=매수가×0.92

현재가 기준으로 매수가/목표가/손절가 계산. 학습 데이터 가격 절대 사용 금지.

아래 JSON만 출력:
{{"시장한줄요약":"string","단타":[{{"종목명":"string","티커":"string","현재가":"string","매수가":"string","목표가":"string","손절가":"string","예상수익률":"string","투자근거":"string","리스크":"string"}}],"스윙":[{{"종목명":"string","티커":"string","현재가":"string","매수가":"string","목표가":"string","손절가":"string","예상수익률":"string","투자근거":"string","리스크":"string"}}],"중장기":[{{"종목명":"string","티커":"string","현재가":"string","매수가":"string","목표가":"string","손절가":"string","예상수익률":"string","투자근거":"string","리스크":"string"}}]}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        return _parse_json_safe(message.content[0].text.strip())
    except Exception as e:
        return {"오류": str(e)}
