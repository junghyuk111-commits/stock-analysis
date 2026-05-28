import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def send_daily_report(gmail_address, app_password, to_address, report_html):
    """Gmail SMTP로 일일 리포트 발송"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 AI 주식 리포트 {datetime.now().strftime('%Y년 %m월 %d일')}"
    msg["From"] = gmail_address
    msg["To"] = to_address

    msg.attach(MIMEText(report_html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, to_address, msg.as_string())
        return True, "발송 성공"
    except smtplib.SMTPAuthenticationError:
        return False, "인증 실패 — 앱 비밀번호를 확인해주세요"
    except Exception as e:
        return False, f"발송 실패: {e}"


def build_report_html(ai_result, market_summary="", date_str=""):
    """AI 분석 결과를 HTML 이메일로 변환"""
    if not date_str:
        date_str = datetime.now().strftime("%Y년 %m월 %d일")

    picks = ai_result.get("추천종목", [])
    market_note = ai_result.get("시장요약", "")
    caution = ai_result.get("오늘주의사항", "")

    strategy_color = {"단타": "#ff6b6b", "스윙": "#ffd93d", "중장기": "#6bcb77"}
    strategy_icon = {"단타": "⚡", "스윙": "📊", "중장기": "🌱"}

    picks_html = ""
    for pick in picks:
        strat = pick.get("전략", "스윙")
        color = strategy_color.get(strat, "#aaa")
        icon = strategy_icon.get(strat, "")
        picks_html += f"""
        <tr>
          <td style="padding:14px; border-bottom:1px solid #2a2a3e;">
            <span style="font-size:1.1em; font-weight:bold; color:#e0e0ff;">
              {pick.get('순위','')}위 {pick.get('종목명','')}
              <span style="font-size:0.85em; color:#888;">({pick.get('티커','')})</span>
            </span>
            <span style="background:{color}22; color:{color}; border:1px solid {color};
                         border-radius:4px; padding:2px 8px; margin-left:8px; font-size:0.8em;">
              {icon} {strat}
            </span>
            <span style="color:#6bcb77; font-size:0.9em; margin-left:8px;">
              예상 {pick.get('예상수익률','')}
            </span>
            <div style="color:#aaa; font-size:0.88em; margin-top:6px; line-height:1.6;">
              {pick.get('추천이유','').replace(chr(10), '<br>')}
            </div>
          </td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0; padding:0; background:#0f0f1a; font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;">
      <div style="max-width:600px; margin:0 auto; padding:20px;">

        <!-- 헤더 -->
        <div style="background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:12px;
                    padding:24px; text-align:center; margin-bottom:16px;
                    border:1px solid #2a2a4e;">
          <div style="font-size:2em;">📈</div>
          <h1 style="color:#e0e0ff; margin:8px 0 4px; font-size:1.4em;">AI 주식 일일 리포트</h1>
          <div style="color:#888; font-size:0.9em;">{date_str}</div>
        </div>

        <!-- 시장 요약 -->
        {"" if not market_note else f'''
        <div style="background:#1a2a1a; border-left:3px solid #6bcb77; border-radius:8px;
                    padding:14px 16px; margin-bottom:12px; color:#b0d4b0; font-size:0.92em;">
          📊 <strong>오늘 시장:</strong> {market_note}
        </div>
        '''}

        <!-- 주의사항 -->
        {"" if not caution else f'''
        <div style="background:#2a1a1a; border-left:3px solid #ff6b6b; border-radius:8px;
                    padding:14px 16px; margin-bottom:16px; color:#d4b0b0; font-size:0.92em;">
          ⚠️ <strong>오늘 주의:</strong> {caution}
        </div>
        '''}

        <!-- 추천 종목 -->
        <div style="background:#1a1a2e; border-radius:12px; border:1px solid #2a2a4e; overflow:hidden;">
          <div style="padding:14px 16px; background:#16213e; color:#e0e0ff; font-weight:bold;">
            💡 오늘의 AI 추천 종목
          </div>
          <table style="width:100%; border-collapse:collapse;">
            {picks_html}
          </table>
        </div>

        <!-- 면책 -->
        <div style="text-align:center; color:#555; font-size:0.78em; margin-top:20px; line-height:1.8;">
          본 리포트는 AI가 생성한 투자 참고 정보입니다.<br>
          투자 손실의 책임은 투자자 본인에게 있습니다.
        </div>

      </div>
    </body>
    </html>
    """
    return html
