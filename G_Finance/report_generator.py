"""
Executive Portfolio Report Generator
Generates standalone, beautifully styled, responsive HTML reports
that can be viewed in any web browser or printed to PDF.
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from i18n import t as tr


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
            <h2>📜 {tr('rep_recent_sales')}</h2>
            <table>
                <thead>
                    <tr>
                        <th>{tr('col_tx_date')}</th>
                        <th>{tr('col_symbol')}</th>
                        <th style="text-align: right;">{tr('rep_shares_sold')}</th>
                        <th style="text-align: right;">{tr('col_buy_price')}</th>
                        <th style="text-align: right;">{tr('rep_gross_proceeds')}</th>
                        <th style="text-align: right;">{tr('rep_net_profit')}</th>
                        <th style="text-align: right;">{tr('rep_net_roi')}</th>
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
    <title>{tr('rep_executive_title')} - {now_str}</title>
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
                <h1>📈 {tr('rep_executive_title')}</h1>
                <div style="font-size: 13px; color: #5f6368; margin-top: 4px;">{tr('rep_valuation_analysis')} ({base_curr})</div>
            </div>
            <div class="meta">
                <div>{tr('rep_report_date')}: <strong>{now_str}</strong></div>
                <div>{tr('rep_base_currency')}: <strong>{base_curr}</strong></div>
                <button class="btn-print" onclick="window.print()">🖨️ {tr('rep_print_pdf')}</button>
            </div>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">{tr('card_total_value')}</div>
                <div class="kpi-value">${tot_val:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">{tr('rep_total_cost_basis')}</div>
                <div class="kpi-value" style="color: #5f6368;">${tot_cost:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">{tr('rep_unrealized_pl')}</div>
                <div class="kpi-value" style="color: {gain_color};">${tot_gain:+,.2f} ({tot_gain_pct:+.2f}%)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">{tr('rep_day_change')}</div>
                <div class="kpi-value" style="color: {day_color};">${day_chg:+,.2f} ({day_chg_pct:+.2f}%)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">{tr('rep_proj_ann_div')}</div>
                <div class="kpi-value" style="color: #1a73e8;">${ann_div:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">{tr('rep_yoc_avg_yield')}</div>
                <div class="kpi-value" style="color: #0f9d58;">{yoc:.2f}% / {div_yield:.2f}%</div>
            </div>
        </div>

        <div class="section">
            <h2>📊 {tr('rep_active_holdings', count=len(holdings))}</h2>
            <table>
                <thead>
                    <tr>
                        <th>{tr('col_symbol')}</th>
                        <th>{tr('col_name')}</th>
                        <th style="text-align: right;">{tr('col_shares')}</th>
                        <th style="text-align: right;">{tr('col_buy_price')}</th>
                        <th style="text-align: right;">{tr('col_current_price')}</th>
                        <th style="text-align: right;">{tr('col_day_change')}</th>
                        <th style="text-align: right;">{tr('col_market_value')}</th>
                        <th style="text-align: right;">{tr('col_unrealized_gain')}</th>
                        <th style="text-align: right;">{tr('col_dividend_yield')}</th>
                        <th style="text-align: right;">{tr('col_annual_div')}</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>

        {sales_section}

        <div class="footer">
            {tr('rep_generated_by')} &bull; {now_str}
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


def generate_period_earnings_report_html(
    period_data: Dict[str, Any],
    filepath: str,
    title: str = "Period Earnings & Performance Report",
) -> bool:
    """
    Generates a professional standalone HTML report summarizing earnings for a specific period
    (This Week, This Month, Monthly breakdown, Weekly breakdown, or Custom Range).
    """
    summary = period_data.get("summary", {})
    portfolio = period_data.get("portfolio", "All Portfolios")
    mode = period_data.get("period_mode", "this_month")
    start_date = period_data.get("start_date")
    end_date = period_data.get("end_date")
    records = period_data.get("records", [])
    breakdown = period_data.get("breakdown", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mode_display_names = {
        "this_week": tr("tf_past_5d", "This Week"),
        "this_month": tr("tf_past_1m", "This Month"),
        "in_months": tr("tab_period_breakdown", "Monthly Performance Breakdown"),
        "in_weeks": tr("tab_period_breakdown", "Weekly Performance Breakdown"),
        "custom": f"{tr('lbl_custom', 'Custom')} ({start_date} ~ {end_date})" if start_date and end_date else tr("lbl_custom", "Custom Period"),
    }
    mode_label = mode_display_names.get(mode, mode.replace("_", " ").title())

    tot_prof = float(summary.get("total_realized_profit", 0.0))
    tot_cost = float(summary.get("total_cost_basis", 0.0))
    tot_sell = float(summary.get("total_sell_proceeds", 0.0))
    tot_buy = float(summary.get("total_buy_volume", 0.0))
    tot_div = float(summary.get("total_dividend", 0.0))
    roi_pct = float(summary.get("net_roi_pct", 0.0))
    b_cnt = int(summary.get("buy_count", 0))
    s_cnt = int(summary.get("sell_count", 0))
    d_cnt = int(summary.get("dividend_count", 0))
    tot_tx = int(summary.get("total_transactions", 0))

    prof_color = "#0f9d58" if tot_prof >= 0 else "#d93025"

    # Build Breakdown Table HTML if breakdown is present
    breakdown_section = ""
    if breakdown:
        b_rows = []
        for b in breakdown:
            b_prof = float(b.get("total_realized_profit", 0.0))
            b_cost = float(b.get("total_cost_basis", 0.0))
            b_sell = float(b.get("total_sell_proceeds", 0.0))
            b_buy = float(b.get("total_buy_volume", 0.0))
            b_roi = float(b.get("net_roi_pct", 0.0))
            b_cnt = int(b.get("total_transactions", 0))
            color = "#0f9d58" if b_prof >= 0 else "#d93025"

            b_rows.append(f"""
                <tr>
                    <td style="font-weight: 600;">{b.get('period_label', '')}</td>
                    <td style="text-align: center;">{b_cnt}</td>
                    <td style="text-align: right; color: #1a73e8;">${b_buy:,.2f}</td>
                    <td style="text-align: right;">${b_sell:,.2f}</td>
                    <td style="text-align: right; color: #5f6368;">${b_cost:,.2f}</td>
                    <td style="text-align: right; font-weight: 700; color: {color};">${b_prof:+,.2f}</td>
                    <td style="text-align: right; font-weight: 600; color: {color};">{b_roi:+.2f}%</td>
                </tr>
            """)
        breakdown_section = f"""
        <div class="section">
            <h2>📅 {tr('tab_period_breakdown')} ({len(breakdown)})</h2>
            <table>
                <thead>
                    <tr>
                        <th>{tr('col_period_interval')}</th>
                        <th style="text-align: center;">{tr('col_trades_count')}</th>
                        <th style="text-align: right;">{tr('col_buy_volume')}</th>
                        <th style="text-align: right;">{tr('col_sell_proceeds')}</th>
                        <th style="text-align: right;">{tr('col_cost_sold')}</th>
                        <th style="text-align: right;">{tr('col_realized_profit')}</th>
                        <th style="text-align: right;">{tr('col_net_roi')}</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(b_rows)}
                </tbody>
            </table>
        </div>
        """

    # Build Transaction Details HTML
    tx_rows = []
    for rec in records:
        t_type = str(rec.get("type", "BUY")).upper()
        p_name = rec.get("portfolio", "")
        sym = rec.get("symbol", "")
        shares = float(rec.get("shares", 0.0) or 0.0)
        price = float(rec.get("price", 0.0) or 0.0)
        tot_amt = float(rec.get("total_amount", 0.0) or 0.0)
        c_basis = float(rec.get("cost_basis", 0.0) or 0.0)
        n_prof = float(rec.get("net_profit", 0.0) or 0.0)
        n_roi = float(rec.get("net_roi_pct", 0.0) or 0.0)
        notes = rec.get("notes", "")

        type_badge = "#1a73e8" if "BUY" in t_type else ("#0f9d58" if "SELL" in t_type else "#9334e6")
        p_color = "#0f9d58" if n_prof >= 0 else "#d93025"
        prof_display = f"${n_prof:+,.2f}" if "SELL" in t_type or "DIVIDEND" in t_type else "-"
        roi_display = f"{n_roi:+.2f}%" if "SELL" in t_type else "-"

        tx_rows.append(f"""
            <tr>
                <td>{rec.get('date', '')}</td>
                <td><span style="background-color: {type_badge}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{t_type}</span></td>
                <td>{p_name}</td>
                <td style="font-weight: 600;">{sym}</td>
                <td style="text-align: right;">{shares:.4f}</td>
                <td style="text-align: right;">${price:,.2f}</td>
                <td style="text-align: right;">${tot_amt:,.2f}</td>
                <td style="text-align: right; color: #5f6368;">${c_basis:,.2f}</td>
                <td style="text-align: right; font-weight: 600; color: {p_color};">{prof_display}</td>
                <td style="text-align: right; font-weight: 600; color: {p_color};">{roi_display}</td>
                <td style="font-size: 12px; color: #5f6368;">{notes}</td>
            </tr>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {portfolio}</title>
    <style>
        :root {{
            --primary-color: #1a73e8;
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #202124;
            --text-muted: #5f6368;
            --border-color: #dadce0;
            --success-color: #0f9d58;
            --danger-color: #d93025;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 24px;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: var(--card-bg);
            padding: 24px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(60,64,67, 0.15);
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{
            margin: 0 0 8px 0;
            font-size: 24px;
            color: var(--primary-color);
        }}
        .header p {{
            margin: 0;
            color: var(--text-muted);
            font-size: 14px;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--card-bg);
            padding: 18px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(60,64,67, 0.15);
            border-left: 4px solid var(--primary-color);
        }}
        .kpi-title {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 20px;
            font-weight: 700;
            color: var(--text-color);
        }}
        .section {{
            background: var(--card-bg);
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(60,64,67, 0.15);
            margin-bottom: 24px;
        }}
        .section h2 {{
            margin-top: 0;
            font-size: 18px;
            border-bottom: 2px solid #f1f3f4;
            padding-bottom: 10px;
            color: #3c4043;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th, td {{
            padding: 10px 12px;
            border-bottom: 1px solid var(--border-color);
            text-align: left;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
            color: var(--text-muted);
        }}
        tr:hover {{
            background-color: #f1f3f4;
        }}
        .footer {{
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid var(--border-color);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>📈 {title}</h1>
                <p><strong>{tr('col_portfolio')}:</strong> {portfolio} &bull; <strong>{tr('rep_period')}:</strong> {mode_label}</p>
            </div>
            <div style="text-align: right;">
                <p><strong>{tr('rep_generated')}:</strong> {now_str}</p>
                <p><strong>{tr('rep_total_tx')}:</strong> {tot_tx}</p>
            </div>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card" style="border-left-color: {prof_color};">
                <div class="kpi-title">{tr('rep_realized_earnings')}</div>
                <div class="kpi-value" style="color: {prof_color};">${tot_prof:+,.2f}</div>
            </div>
            <div class="kpi-card" style="border-left-color: {prof_color};">
                <div class="kpi-title">{tr('rep_net_roi_capital')}</div>
                <div class="kpi-value" style="color: {prof_color};">{roi_pct:+.2f}%</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">{tr('rep_total_sales_proceeds')}</div>
                <div class="kpi-value">${tot_sell:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">{tr('rep_cost_basis_sold')}</div>
                <div class="kpi-value" style="color: #5f6368;">${tot_cost:,.2f}</div>
            </div>
            <div class="kpi-card" style="border-left-color: #1a73e8;">
                <div class="kpi-title">{tr('rep_buy_volume')}</div>
                <div class="kpi-value" style="color: #1a73e8;">${tot_buy:,.2f}</div>
            </div>
            <div class="kpi-card" style="border-left-color: #9334e6;">
                <div class="kpi-title">{tr('rep_trade_counts')}</div>
                <div class="kpi-value" style="font-size: 16px;">{b_cnt} Buys / {s_cnt} Sells / {d_cnt} Divs</div>
            </div>
        </div>

        {breakdown_section}

        <div class="section">
            <h2>📜 {tr('rep_tx_records_count', count=len(records))}</h2>
            <table>
                <thead>
                    <tr>
                        <th>{tr('col_tx_date')}</th>
                        <th>{tr('col_tx_type')}</th>
                        <th>{tr('col_tx_port')}</th>
                        <th>{tr('col_tx_sym')}</th>
                        <th style="text-align: right;">{tr('col_tx_shares')}</th>
                        <th style="text-align: right;">{tr('col_tx_price')}</th>
                        <th style="text-align: right;">{tr('col_tx_total')}</th>
                        <th style="text-align: right;">{tr('col_cost_basis')}</th>
                        <th style="text-align: right;">{tr('col_tx_profit')}</th>
                        <th style="text-align: right;">{tr('col_tx_roi')}</th>
                        <th>{tr('col_notes')}</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(tx_rows) if tx_rows else f'<tr><td colspan="11" style="text-align: center; color: #888;">{tr("rep_no_tx_found")}</td></tr>'}
                </tbody>
            </table>
        </div>

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
        print(f"Error generating period earnings report: {e}")
        return False
