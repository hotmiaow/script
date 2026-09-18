"""
Executive Portfolio Report Generator
Generates standalone, beautifully styled, responsive HTML reports
that can be viewed in any web browser or printed to PDF.
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional


def generate_html_report(
    holdings: List[Dict[str, Any]],
    portfolio_metrics: Dict[str, Any],
    sales_history: Optional[List[Dict[str, Any]]] = None,
    filepath: str = "portfolio_report.html",
) -> bool:
    """
    Generates a professional HTML portfolio executive summary report.
    """
    if sales_history is None:
        sales_history = []

    now_str = datetime.now().strftime("%B %d, %Y - %I:%M %p")
    base_curr = portfolio_metrics.get("base_currency", "USD")
    tot_val = portfolio_metrics.get("total_value", 0.0)
    tot_cost = portfolio_metrics.get("total_cost", 0.0)
    tot_gain = portfolio_metrics.get("total_gain", 0.0)
    tot_gain_pct = portfolio_metrics.get("total_gain_pct", 0.0)
    ann_div = portfolio_metrics.get("total_annual_div", 0.0)
    mo_div = portfolio_metrics.get("total_monthly_div", 0.0)
    yoc = portfolio_metrics.get("portfolio_yoc", 0.0)
    div_yield = portfolio_metrics.get("overall_div_yield", 0.0)
    day_chg = portfolio_metrics.get("total_day_change", 0.0)
    day_chg_pct = portfolio_metrics.get("total_day_change_pct", 0.0)

    gain_color = "#0f9d58" if tot_gain >= 0 else "#d93025"
    day_color = "#0f9d58" if day_chg >= 0 else "#d93025"

    # Build holdings rows
    rows_html = []
    for h in holdings:
        unrealized = float(h.get("unrealized_gain", 0.0))
        unrealized_pct = float(h.get("unrealized_gain_pct", 0.0))
        h_color = "#0f9d58" if unrealized >= 0 else "#d93025"
        chg = h.get("change")
        chg_pct = h.get("change_percent")
        chg_str = f"{chg:+.2f} ({chg_pct:+.2f}%)" if chg is not None and chg_pct is not None else "-"
        chg_color = "#0f9d58" if (chg or 0) >= 0 else "#d93025"
        curr = h.get("currency", base_curr)

        rows_html.append(f"""
        <tr>
            <td style="font-weight: bold; color: #1a73e8;">{h.get('symbol', '')}</td>
            <td>{h.get('name', '')}</td>
            <td style="text-align: right;">{float(h.get('shares', 0.0)):.4g}</td>
            <td style="text-align: right;">${float(h.get('buy_price', 0.0)):,.2f}</td>
            <td style="text-align: right; font-weight: 600;">${float(h.get('current_price', 0.0)):,.2f} {curr}</td>
            <td style="text-align: right; color: {chg_color}; font-weight: 500;">{chg_str}</td>
            <td style="text-align: right; font-weight: bold;">${float(h.get('market_value', 0.0)):,.2f}</td>
            <td style="text-align: right; color: {h_color}; font-weight: bold;">${unrealized:+,.2f} ({unrealized_pct:+.2f}%)</td>
            <td style="text-align: right;">{float(h.get('dividend_yield', 0.0)):.2f}%</td>
            <td style="text-align: right; color: #1a73e8; font-weight: 600;">${float(h.get('annual_dividend', 0.0)):,.2f}</td>
        </tr>
        """)

    # Build sales rows
    sales_rows = []
    for s in sales_history[:20]:
        prof = float(s.get("net_profit", 0.0))
        p_col = "#0f9d58" if prof >= 0 else "#d93025"
        sales_rows.append(f"""
        <tr>
            <td>{s.get('date', '')}</td>
            <td style="font-weight: bold;">{s.get('symbol', '')}</td>
            <td style="text-align: right;">{float(s.get('shares_to_sell', 0.0)):.4g}</td>
            <td style="text-align: right;">${float(s.get('sell_price', 0.0)):,.2f}</td>
            <td style="text-align: right;">${float(s.get('gross_proceeds', 0.0)):,.2f}</td>
            <td style="text-align: right; color: {p_col}; font-weight: bold;">${prof:+,.2f}</td>
            <td style="text-align: right; color: {p_col}; font-weight: bold;">{float(s.get('net_roi_pct', 0.0)):+.2f}%</td>
        </tr>
        """)

    sales_section = ""
    if sales_rows:
        sales_section = f"""
        <div class="section">
            <h2>📜 Recent Realized Sales History</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Symbol</th>
                        <th style="text-align: right;">Shares Sold</th>
                        <th style="text-align: right;">Sell Price</th>
                        <th style="text-align: right;">Gross Proceeds</th>
                        <th style="text-align: right;">Net Profit</th>
                        <th style="text-align: right;">Net ROI</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(sales_rows)}
                </tbody>
            </table>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portfolio Executive Summary - {now_str}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8f9fa;
            color: #202124;
            padding: 32px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #e8eaed;
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        .header h1 {{
            font-size: 24px;
            color: #1a73e8;
            font-weight: 700;
        }}
        .header .meta {{
            text-align: right;
            font-size: 13px;
            color: #5f6368;
        }}
        .btn-print {{
            background: #1a73e8;
            color: #ffffff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 8px;
        }}
        .btn-print:hover {{ background: #1557b0; }}
        
        /* KPI Cards */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .kpi-card {{
            background: #f8f9fa;
            border: 1px solid #e8eaed;
            border-radius: 8px;
            padding: 16px;
        }}
        .kpi-title {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #5f6368;
            font-weight: 600;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 20px;
            font-weight: 700;
            color: #202124;
        }}
        
        .section {{ margin-bottom: 32px; }}
        .section h2 {{
            font-size: 17px;
            font-weight: 600;
            margin-bottom: 12px;
            color: #202124;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            border: 1px solid #e8eaed;
            border-radius: 8px;
            overflow: hidden;
        }}
        th {{
            background: #f1f3f4;
            color: #202124;
            font-weight: 600;
            text-align: left;
            padding: 12px 14px;
            border-bottom: 1px solid #e8eaed;
        }}
        td {{
            padding: 12px 14px;
            border-bottom: 1px solid #e8eaed;
        }}
        tr:nth-child(even) {{ background: #fafafa; }}
        tr:hover {{ background: #f8fafd; }}

        .footer {{
            text-align: center;
            font-size: 12px;
            color: #5f6368;
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #e8eaed;
        }}

        @media print {{
            body {{ background: #ffffff; padding: 0; }}
            .container {{ box-shadow: none; padding: 0; }}
            .btn-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>📈 Google Finance Portfolio Executive Report</h1>
                <div style="font-size: 13px; color: #5f6368; margin-top: 4px;">Valuation & Performance Analysis ({base_curr})</div>
            </div>
            <div class="meta">
                <div>Report Date: <strong>{now_str}</strong></div>
                <div>Base Currency: <strong>{base_curr}</strong></div>
                <button class="btn-print" onclick="window.print()">🖨️ Print / Save as PDF</button>
            </div>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">Portfolio Value</div>
                <div class="kpi-value">${tot_val:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Total Cost Basis</div>
                <div class="kpi-value" style="color: #5f6368;">${tot_cost:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Unrealized Profit/Loss</div>
                <div class="kpi-value" style="color: {gain_color};">${tot_gain:+,.2f} ({tot_gain_pct:+.2f}%)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Day Change</div>
                <div class="kpi-value" style="color: {day_color};">${day_chg:+,.2f} ({day_chg_pct:+.2f}%)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Projected Annual Dividend</div>
                <div class="kpi-value" style="color: #1a73e8;">${ann_div:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Yield on Cost / Avg Yield</div>
                <div class="kpi-value" style="color: #0f9d58;">{yoc:.2f}% / {div_yield:.2f}%</div>
            </div>
        </div>

        <div class="section">
            <h2>📊 Active Portfolio Holdings ({len(holdings)} positions)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Company Name</th>
                        <th style="text-align: right;">Shares</th>
                        <th style="text-align: right;">Buy Price</th>
                        <th style="text-align: right;">Current Price</th>
                        <th style="text-align: right;">Day Change</th>
                        <th style="text-align: right;">Market Value</th>
                        <th style="text-align: right;">Profit / Loss</th>
                        <th style="text-align: right;">Div Yield</th>
                        <th style="text-align: right;">Est. Ann Div</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>

        {sales_section}

        <div class="footer">
            Generated by Google Finance Portfolio Tracker & Financial Calculator &bull; Local Data Persistence &bull; {now_str}
        </div>
    </div>
</body>
</html>
"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        return True
    except Exception as e:
        print(f"Error generating report: {e}")
        return False
