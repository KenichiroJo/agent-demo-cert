"""
売上予測レポート Word 出力モジュール

HTML ベースの .doc ファイルを生成（python-docx 不要）
Microsoft Word は HTML 形式の .doc を正しく開ける
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def generate_forecast_report_html(
    *,
    store_type: str,
    start_date: str,
    end_date: str,
    forecast_data: list[dict[str, Any]],
    analysis: dict[str, Any] | None = None,
) -> str:
    """
    売上予測レポートを Word 互換 HTML で生成

    Returns:
        HTML string (.doc として保存可能)
    """
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    # テーブルデータ構築
    table_rows = ""
    for row in forecast_data:
        date_str = str(row.get("date", ""))[:7]
        actual = row.get("actual_sales")
        predicted = row.get("predicted_sales")
        error = row.get("error")
        pct_error = row.get("pct_error")

        a_str = f"{actual:.2f}" if actual is not None and actual == actual else "-"
        p_str = f"{predicted:.2f}" if predicted is not None and predicted == predicted else "-"
        e_str = f"{error:+.3f}" if error is not None and error == error else "-"
        pct_str = f"{pct_error:+.1f}%" if pct_error is not None and pct_error == pct_error else "-"

        # 誤差が大きい行をハイライト
        highlight = ""
        if pct_error is not None and pct_error == pct_error and abs(pct_error) > 5:
            highlight = ' style="background-color: #FFF3CD;"'

        table_rows += f"""
        <tr{highlight}>
            <td>{date_str}</td>
            <td style="text-align:right;">{a_str}</td>
            <td style="text-align:right;">{p_str}</td>
            <td style="text-align:right;">{e_str}</td>
            <td style="text-align:right;">{pct_str}</td>
        </tr>"""

    # KPI計算
    with_pred = [r for r in forecast_data
                 if r.get("predicted_sales") is not None
                 and r.get("actual_sales") is not None
                 and r.get("predicted_sales") == r.get("predicted_sales")
                 and r.get("actual_sales") == r.get("actual_sales")]

    rmse_str = mae_str = mape_str = max_err_str = "-"
    if with_pred:
        errors = [abs(r["actual_sales"] - r["predicted_sales"]) for r in with_pred]
        rmse = (sum(e**2 for e in errors) / len(errors)) ** 0.5
        mae = sum(errors) / len(errors)
        pct_errors = [abs(r.get("pct_error", 0) or 0) for r in with_pred if r.get("pct_error") is not None]
        mape = sum(pct_errors) / len(pct_errors) if pct_errors else 0
        max_err = max(errors)
        rmse_str = f"{rmse:.3f}"
        mae_str = f"{mae:.3f}"
        mape_str = f"{mape:.1f}%"
        max_err_str = f"{max_err:.3f}"

    # 分析テキスト
    analysis_section = ""
    if analysis:
        summary = analysis.get("analysis", {}).get("summary", "")
        if summary:
            # Markdown → 簡易HTML変換
            html_summary = summary.replace("\n\n", "</p><p>").replace("\n", "<br>")
            html_summary = html_summary.replace("## ", "<h3>").replace("### ", "<h4>")
            # 太字
            import re
            html_summary = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_summary)

            confidence = analysis.get("confidence_score", 0)
            analysis_section = f"""
    <div style="page-break-before: always;"></div>

    <h2 style="color: #4A3090;">AI 誤差分析レポート</h2>

    <table style="width:100%; margin-bottom:20px;">
        <tr>
            <td style="background:#F0F0F0; padding:8px;"><strong>対象業態:</strong> {analysis.get('store_type', store_type)}</td>
            <td style="background:#F0F0F0; padding:8px;"><strong>対象月:</strong> {analysis.get('date', '-')}</td>
            <td style="background:#F0F0F0; padding:8px;"><strong>分析信頼度:</strong> {confidence:.0%}</td>
        </tr>
    </table>

    <div style="border:1px solid #DDD; padding:15px; border-radius:5px; line-height:1.8;">
        <p>{html_summary}</p>
    </div>
    """

    return f"""<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
    <meta charset="utf-8">
    <title>売上予測レポート - {store_type}</title>
    <!--[if gte mso 9]>
    <xml>
        <w:WordDocument>
            <w:View>Print</w:View>
            <w:Zoom>100</w:Zoom>
            <w:DoNotOptimizeForBrowser/>
        </w:WordDocument>
    </xml>
    <![endif]-->
    <style>
        body {{
            font-family: 'Yu Gothic', 'Hiragino Sans', 'Meiryo', sans-serif;
            font-size: 10.5pt;
            color: #333;
            margin: 30px;
            line-height: 1.6;
        }}
        h1 {{
            font-size: 18pt;
            color: #2D2070;
            border-bottom: 3px solid #6B46C1;
            padding-bottom: 8px;
            margin-bottom: 5px;
        }}
        h2 {{
            font-size: 14pt;
            color: #4A3090;
            margin-top: 25px;
        }}
        h3 {{
            font-size: 12pt;
            color: #5B4BA0;
            margin-top: 15px;
        }}
        .meta {{
            color: #888;
            font-size: 9pt;
            margin-bottom: 20px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 10px 0;
        }}
        th {{
            background-color: #4A3090;
            color: white;
            padding: 8px 12px;
            text-align: left;
            font-size: 9.5pt;
        }}
        td {{
            border: 1px solid #DDD;
            padding: 6px 12px;
            font-size: 9.5pt;
        }}
        tr:nth-child(even) {{
            background-color: #F9F9F9;
        }}
        .kpi-box {{
            display: inline-block;
            border: 1px solid #DDD;
            border-radius: 5px;
            padding: 10px 20px;
            margin: 5px;
            text-align: center;
            min-width: 120px;
        }}
        .kpi-label {{
            font-size: 8.5pt;
            color: #888;
        }}
        .kpi-value {{
            font-size: 14pt;
            font-weight: bold;
            color: #4A3090;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 10px;
            border-top: 1px solid #DDD;
            font-size: 8pt;
            color: #AAA;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>📊 売上予測レポート</h1>
    <div class="meta">
        業態: <strong>{store_type}</strong> ｜
        期間: {start_date} 〜 {end_date} ｜
        生成日時: {now}
    </div>

    <h2>予測精度サマリ</h2>
    <div>
        <div class="kpi-box">
            <div class="kpi-label">RMSE</div>
            <div class="kpi-value">{rmse_str}</div>
            <div class="kpi-label">億円</div>
        </div>
        <div class="kpi-box">
            <div class="kpi-label">MAE</div>
            <div class="kpi-value">{mae_str}</div>
            <div class="kpi-label">億円</div>
        </div>
        <div class="kpi-box">
            <div class="kpi-label">MAPE</div>
            <div class="kpi-value">{mape_str}</div>
        </div>
        <div class="kpi-box">
            <div class="kpi-label">最大誤差</div>
            <div class="kpi-value">{max_err_str}</div>
            <div class="kpi-label">億円</div>
        </div>
    </div>

    <h2>月別 予測 vs 実績</h2>
    <table>
        <thead>
            <tr>
                <th>年月</th>
                <th style="text-align:right;">実績 (億円)</th>
                <th style="text-align:right;">予測 (億円)</th>
                <th style="text-align:right;">誤差 (億円)</th>
                <th style="text-align:right;">誤差率</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>

    {analysis_section}

    <div class="footer">
        Powered by DataRobot AutoTS + LLM Gateway ｜ 本レポートは自動生成されています
    </div>
</body>
</html>"""
