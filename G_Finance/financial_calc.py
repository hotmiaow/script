"""
Financial Calculator Engine
Performs precise calculations for:
- Dividend income, yield on cost, quarterly/monthly projections
- Dividend Reinvestment (DRIP) multi-year compounding simulation
- Stock division / split adjustments (ratios e.g. 2:1, 4:1, 1:5)
- Selling calculations: gross proceeds, capital gains/loss, commissions, taxes, net profit, ROI
- Breakeven price and Target Profit price analysis
"""

import calendar
import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple


def calc_holding_summary(
    shares: float,
    buy_price: float,
    current_price: float,
    div_yield: float = 0.0,
    annual_div_per_share: float = 0.0,
) -> Dict[str, Any]:
    """
    Computes holding totals, unrealized gain/loss, and expected dividend returns.
    """
    shares = max(0.0, float(shares))
    buy_price = max(0.0, float(buy_price))
    current_price = max(0.0, float(current_price))

    cost_basis = round(shares * buy_price, 2)
    market_value = round(shares * current_price, 2)
    unrealized_gain = round(market_value - cost_basis, 2)
    unrealized_gain_pct = round((unrealized_gain / cost_basis * 100), 2) if cost_basis > 0 else 0.0

    # Dividend computations
    if annual_div_per_share <= 0.0 and div_yield > 0:
        annual_div_per_share = current_price * (div_yield / 100.0)

    annual_dividend = round(shares * annual_div_per_share, 2)
    quarterly_dividend = round(annual_dividend / 4.0, 2)
    monthly_dividend = round(annual_dividend / 12.0, 2)
    
    # Yield on cost
    yield_on_cost = round((annual_div_per_share / buy_price * 100), 2) if buy_price > 0 else 0.0

    return {
        "shares": shares,
        "buy_price": buy_price,
        "current_price": current_price,
        "cost_basis": cost_basis,
        "market_value": market_value,
        "unrealized_gain": unrealized_gain,
        "unrealized_gain_pct": unrealized_gain_pct,
        "annual_div_per_share": round(annual_div_per_share, 4),
        "annual_dividend": annual_dividend,
        "quarterly_dividend": quarterly_dividend,
        "monthly_dividend": monthly_dividend,
        "yield_on_cost": yield_on_cost,
    }


def calc_dividend_projection(
    shares: float,
    current_price: float,
    div_yield: float,
    annual_div_per_share: float = 0.0,
    buy_price: float = 0.0,
) -> Dict[str, Any]:
    """
    Detailed dividend breakdown for a given share quantity and stock price.
    """
    shares = max(0.0, float(shares))
    current_price = max(0.0, float(current_price))
    div_yield = max(0.0, float(div_yield))

    if annual_div_per_share <= 0.0 and div_yield > 0:
        annual_div_per_share = current_price * (div_yield / 100.0)

    quarterly_per_share = annual_div_per_share / 4.0

    annual_total = shares * annual_div_per_share
    quarterly_total = annual_total / 4.0
    monthly_total = annual_total / 12.0

    yield_on_cost = (annual_div_per_share / buy_price * 100) if buy_price > 0 else div_yield

    return {
        "shares": shares,
        "current_price": current_price,
        "div_yield_pct": round(div_yield, 2),
        "annual_div_per_share": round(annual_div_per_share, 4),
        "quarterly_div_per_share": round(quarterly_per_share, 4),
        "annual_total": round(annual_total, 2),
        "quarterly_total": round(quarterly_total, 2),
        "monthly_total": round(monthly_total, 2),
        "yield_on_cost": round(yield_on_cost, 2),
    }


def calc_drip_simulation(
    initial_shares: float,
    initial_price: float,
    div_yield_pct: float,
    div_growth_pct: float = 3.0,
    price_growth_pct: float = 6.0,
    monthly_contribution: float = 0.0,
    years: int = 10,
) -> List[Dict[str, Any]]:
    """
    Simulates Dividend Reinvestment Plan (DRIP) growth compounding year by year.
    """
    years = max(1, min(50, int(years)))
    shares = float(initial_shares)
    price = float(initial_price)
    div_per_share = price * (div_yield_pct / 100.0)
    
    total_invested = shares * price
    history = []

    for year in range(1, years + 1):
        # Additional monthly contributions invested across the year
        if monthly_contribution > 0:
            annual_contrib = monthly_contribution * 12.0
            total_invested += annual_contrib
            # assume purchased at average price this year
            shares += annual_contrib / price

        # Annual dividend generated
        annual_div = shares * div_per_share
        
        # Reinvest dividend into more shares
        new_shares_from_drip = (annual_div / price) if price > 0 else 0.0
        shares += new_shares_from_drip

        ending_value = shares * price

        history.append({
            "year": year,
            "stock_price": round(price, 2),
            "shares": round(shares, 4),
            "dividend_per_share": round(div_per_share, 4),
            "annual_dividend": round(annual_div, 2),
            "portfolio_value": round(ending_value, 2),
            "total_invested": round(total_invested, 2),
            "total_profit": round(ending_value - total_invested, 2),
        })

        # Apply annual growth rates for next year
        price *= (1 + price_growth_pct / 100.0)
        div_per_share *= (1 + div_growth_pct / 100.0)

    return history


def calc_stock_split(
    shares: float,
    buy_price: float,
    ratio_from: float,
    ratio_to: float,
) -> Dict[str, Any]:
    """
    Calculates stock division / split (e.g. 2:1 split -> ratio_from=1, ratio_to=2).
    Reverse split: e.g. 1-for-10 -> ratio_from=10, ratio_to=1.
    Total value and total cost basis remain invariant.
    """
    shares = max(0.0, float(shares))
    buy_price = max(0.0, float(buy_price))
    ratio_from = max(0.001, float(ratio_from))
    ratio_to = max(0.001, float(ratio_to))

    multiplier = ratio_to / ratio_from
    new_shares = round(shares * multiplier, 6)
    new_buy_price = round(buy_price / multiplier, 4) if multiplier > 0 else buy_price

    original_basis = round(shares * buy_price, 2)
    new_basis = round(new_shares * new_buy_price, 2)

    return {
        "original_shares": shares,
        "original_buy_price": buy_price,
        "original_basis": original_basis,
        "split_ratio": f"{ratio_to:g}:{ratio_from:g}",
        "multiplier": multiplier,
        "new_shares": new_shares,
        "new_buy_price": new_buy_price,
        "new_basis": new_basis,
    }


def calc_selling_proceeds(
    shares_to_sell: float,
    buy_price: float,
    sell_price: float,
    commission_flat: float = 0.0,
    commission_pct: float = 0.0,
    tax_rate_pct: float = 0.0,
    commission_min: float = 0.0,
) -> Dict[str, Any]:
    """
    Comprehensive selling calculation:
    - Gross proceeds
    - Cost basis of sold shares
    - Broker fees / commission (flat + %, with optional minimum commission)
    - Realized gain/loss before tax
    - Estimated capital gains tax
    - Net proceeds
    - Net profit after all deductions
    - Net Return on Investment (ROI %)
    """
    shares_to_sell = max(0.0, float(shares_to_sell))
    buy_price = max(0.0, float(buy_price))
    sell_price = max(0.0, float(sell_price))
    commission_flat = max(0.0, float(commission_flat))
    commission_pct = max(0.0, float(commission_pct))
    commission_min = max(0.0, float(commission_min))
    tax_rate_pct = max(0.0, float(tax_rate_pct))

    gross_proceeds = round(shares_to_sell * sell_price, 2)
    cost_basis = round(shares_to_sell * buy_price, 2)

    # Commission with minimum threshold check
    commission_fee = commission_flat + (gross_proceeds * commission_pct / 100.0)
    if commission_min > 0 and commission_fee < commission_min and gross_proceeds > 0:
        commission_fee = commission_min
    commission_fee = round(commission_fee, 2)

    # Gross realized gain
    gross_gain = round(gross_proceeds - cost_basis - commission_fee, 2)

    # Capital gains tax applies only if gross gain is positive
    estimated_tax = 0.0
    if gross_gain > 0 and tax_rate_pct > 0:
        estimated_tax = round(gross_gain * (tax_rate_pct / 100.0), 2)

    net_proceeds = round(gross_proceeds - commission_fee - estimated_tax, 2)
    net_profit = round(net_proceeds - cost_basis, 2)

    net_roi_pct = round((net_profit / cost_basis * 100), 2) if cost_basis > 0 else 0.0

    return {
        "shares_to_sell": shares_to_sell,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "gross_proceeds": gross_proceeds,
        "cost_basis": cost_basis,
        "commission_fee": commission_fee,
        "gross_gain": gross_gain,
        "tax_rate_pct": tax_rate_pct,
        "estimated_tax": estimated_tax,
        "net_proceeds": net_proceeds,
        "net_profit": net_profit,
        "net_roi_pct": net_roi_pct,
    }


def calc_breakeven_sell_price(
    shares: float,
    buy_price: float,
    commission_flat: float = 0.0,
    commission_pct: float = 0.0,
) -> float:
    """
    Calculates exact sell price per share required to break even after commissions.
    Gross Proceeds * (1 - comm_pct/100) - comm_flat = shares * buy_price
    shares * P * (1 - c) - F = shares * B
    P = (shares * B + F) / (shares * (1 - c))
    """
    shares = float(shares)
    buy_price = float(buy_price)
    if shares <= 0:
        return buy_price

    factor = 1.0 - (commission_pct / 100.0)
    if factor <= 0:
        return 0.0

    target = (shares * buy_price + commission_flat) / (shares * factor)
    return round(target, 4)


def calc_target_profit_sell_price(
    shares: float,
    buy_price: float,
    target_profit_dollars: float = 0.0,
    target_roi_pct: float = 0.0,
    commission_flat: float = 0.0,
    commission_pct: float = 0.0,
    tax_rate_pct: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculates target sell price to achieve desired net profit or target ROI.
    """
    shares = float(shares)
    buy_price = float(buy_price)
    cost_basis = shares * buy_price

    if target_roi_pct > 0 and target_profit_dollars <= 0:
        target_profit_dollars = cost_basis * (target_roi_pct / 100.0)

    # Net Profit = (Gross Proceeds - comm - basis) * (1 - tax)
    # Target Profit = (shares * P * (1 - comm_pct) - comm_flat - cost_basis) * (1 - tax_rate)
    # If profit is desired:
    tax_factor = (1.0 - tax_rate_pct / 100.0) if tax_rate_pct < 100 else 1.0
    gross_gain_needed = (target_profit_dollars / tax_factor) if tax_factor > 0 else target_profit_dollars

    factor = 1.0 - (commission_pct / 100.0)
    if factor <= 0 or shares <= 0:
        return {"target_sell_price": 0.0, "target_profit": target_profit_dollars}

    required_proceeds = cost_basis + gross_gain_needed + commission_flat
    target_sell_price = required_proceeds / (shares * factor)

    return {
        "shares": shares,
        "cost_basis": round(cost_basis, 2),
        "target_profit_dollars": round(target_profit_dollars, 2),
        "target_sell_price": round(target_sell_price, 4),
        "gross_proceeds_at_target": round(shares * target_sell_price, 2),
    }


def calc_portfolio_metrics(
    holdings: List[Dict[str, Any]],
    base_currency: str = "USD",
    fx_rates: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Computes portfolio-wide analytics, concentration weights, and multi-currency metrics.
    fx_rates maps currency code e.g. 'CNY' to conversion rate into base_currency (e.g. 1 CNY = 0.14 USD).
    """
    if fx_rates is None:
        fx_rates = {}

    total_value = 0.0
    total_cost = 0.0
    total_annual_div = 0.0
    total_day_change = 0.0

    alloc_map: Dict[str, Dict[str, Any]] = {}

    for h in holdings:
        shares = float(h.get("shares", 0.0))
        cur_p = float(h.get("current_price", 0.0))
        buy_p = float(h.get("buy_price", 0.0))
        chg = float(h.get("change") or 0.0)
        curr = str(h.get("currency", base_currency)).upper()

        rate = 1.0 if curr == base_currency.upper() else fx_rates.get(curr, 1.0)

        mkt_val = shares * cur_p * rate
        basis = shares * buy_p * rate
        ann_div = float(h.get("annual_dividend", 0.0)) * rate
        day_chg = shares * chg * rate

        total_value += mkt_val
        total_cost += basis
        total_annual_div += ann_div
        total_day_change += day_chg

        raw_sym = str(h.get("symbol", "")).strip()
        sym_key = raw_sym.upper()
        if not sym_key:
            continue
        name = str(h.get("name", "")).strip()
        h_unreal_pct = float(h.get("unrealized_gain_pct", 0.0))

        if sym_key in alloc_map:
            entry = alloc_map[sym_key]
            entry["value_base"] += mkt_val
            entry["cost_basis"] += basis
            entry["total_shares"] += shares
            entry["annual_dividend"] += ann_div
            entry["day_change"] += day_chg
            if not entry["name"] and name:
                entry["name"] = name
        else:
            alloc_map[sym_key] = {
                "symbol": raw_sym,
                "name": name,
                "value_base": mkt_val,
                "cost_basis": basis,
                "total_shares": shares,
                "annual_dividend": ann_div,
                "day_change": day_chg,
                "currency": base_currency,
                "rate_used": rate,
                "fallback_pct": h_unreal_pct,
            }

    allocations = []
    best_holding = None
    worst_holding = None

    for entry in alloc_map.values():
        v_base = round(entry["value_base"], 2)
        c_basis = round(entry["cost_basis"], 2)
        wt = round((v_base / total_value * 100), 2) if total_value > 0 else 0.0
        gain = v_base - c_basis
        if c_basis > 0:
            gain_pct = round((gain / c_basis * 100), 2)
        else:
            gain_pct = entry.get("fallback_pct", 0.0)

        item = {
            "symbol": entry["symbol"],
            "name": entry["name"],
            "value_base": v_base,
            "cost_basis": c_basis,
            "shares": entry["total_shares"],
            "annual_dividend": round(entry["annual_dividend"], 2),
            "day_change": round(entry["day_change"], 2),
            "currency": entry["currency"],
            "rate_used": entry["rate_used"],
            "weight_pct": wt,
            "unrealized_gain": round(gain, 2),
            "unrealized_gain_pct": gain_pct,
        }
        allocations.append(item)

        if best_holding is None or gain_pct > float(best_holding.get("unrealized_gain_pct", -999999)):
            best_holding = item
        if worst_holding is None or gain_pct < float(worst_holding.get("unrealized_gain_pct", 999999)):
            worst_holding = item

    allocations.sort(key=lambda x: x["value_base"], reverse=True)

    # Calculate currency exposure
    curr_map: Dict[str, float] = {}
    for h in holdings:
        shares = float(h.get("shares", 0.0))
        cur_p = float(h.get("current_price", 0.0))
        curr = str(h.get("currency", base_currency)).upper()
        rate = 1.0 if curr == base_currency.upper() else fx_rates.get(curr, 1.0)
        mkt_val = shares * cur_p * rate
        curr_map[curr] = curr_map.get(curr, 0.0) + mkt_val

    currency_allocations = []
    for c_code, c_val in sorted(curr_map.items(), key=lambda x: x[1], reverse=True):
        c_wt = round((c_val / total_value * 100), 2) if total_value > 0 else 0.0
        currency_allocations.append({
            "currency": c_code,
            "value_base": round(c_val, 2),
            "weight_pct": c_wt,
        })

    # Calculate sector diversification
    sector_map: Dict[str, float] = {}
    for h in holdings:
        shares = float(h.get("shares", 0.0))
        cur_p = float(h.get("current_price", 0.0))
        curr = str(h.get("currency", base_currency)).upper()
        rate = 1.0 if curr == base_currency.upper() else fx_rates.get(curr, 1.0)
        mkt_val = shares * cur_p * rate
        sec = (h.get("sector") or "").strip()
        if not sec:
            sec = infer_holding_sector(h.get("symbol", ""), h.get("name", ""))
        sector_map[sec] = sector_map.get(sec, 0.0) + mkt_val

    sector_allocations = []
    for s_name, s_val in sorted(sector_map.items(), key=lambda x: x[1], reverse=True):
        s_wt = round((s_val / total_value * 100), 2) if total_value > 0 else 0.0
        sector_allocations.append({
            "sector": s_name,
            "value_base": round(s_val, 2),
            "weight_pct": s_wt,
        })

    total_gain = total_value - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0.0
    portfolio_yoc = (total_annual_div / total_cost * 100) if total_cost > 0 else 0.0
    overall_div_yield = (total_annual_div / total_value * 100) if total_value > 0 else 0.0

    prev_day_val = total_value - total_day_change
    total_day_change_pct = (total_day_change / prev_day_val * 100) if prev_day_val > 0 else 0.0
    top_concentration = allocations[0]["weight_pct"] if allocations else 0.0

    return {
        "base_currency": base_currency,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_gain": round(total_gain, 2),
        "total_gain_pct": round(total_gain_pct, 2),
        "total_annual_div": round(total_annual_div, 2),
        "total_monthly_div": round(total_annual_div / 12.0, 2),
        "portfolio_yoc": round(portfolio_yoc, 2),
        "overall_div_yield": round(overall_div_yield, 2),
        "total_day_change": round(total_day_change, 2),
        "total_day_change_pct": round(total_day_change_pct, 2),
        "best_performer": best_holding,
        "worst_performer": worst_holding,
        "allocations": allocations,
        "currency_allocations": currency_allocations,
        "sector_allocations": sector_allocations,
        "top_concentration_pct": top_concentration,
    }


def infer_holding_sector(symbol: str, name: str = "") -> str:
    """Infers standard industry sector category from ticker symbol or company name."""
    s = (symbol or "").upper().strip()
    n = (name or "").upper().strip()
    pure_sym = s.split(":")[0].split(".")[0]

    if any(k in pure_sym for k in ["VOO", "VFV", "VGRO", "SPY", "IVV", "QQQ", "XEF", "XIU", "VCN", "EEM", "VTI"]):
        return "Index ETF"
    if any(k in pure_sym for k in ["ZAG", "BND", "AGG", "TLT", "IEF", "XBB", "VAB"]):
        return "Fixed Income / Bond"
    if any(k in pure_sym for k in ["AAPL", "MSFT", "GOOG", "GOOGL", "NVDA", "TSLA", "AMD", "INTC", "NOK", "CSCO", "ORCL", "CRM", "ADBE"]):
        return "Technology"
    if any(k in pure_sym for k in ["HSBC", "JPM", "BAC", "C", "WFC", "GS", "MS", "TD", "RY", "BNS", "BMO", "CM"]):
        return "Financial Services"
    if any(k in pure_sym for k in ["ALB", "LIN", "APD", "NEM", "GOLD", "ABX", "FCX", "SCCO"]):
        return "Basic Materials"
    if any(k in pure_sym for k in ["XOM", "CVX", "COP", "SHEL", "BP", "TTE", "ENB", "CNQ", "SU", "TRP"]):
        return "Energy"
    if any(k in pure_sym for k in ["JNJ", "PFE", "UNH", "ABBV", "MRK", "LLY", "TMO", "ABT"]):
        return "Healthcare"
    if any(k in pure_sym for k in ["AMZN", "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT", "PG", "KO", "PEP"]):
        return "Consumer Goods"
    if any(k in pure_sym for k in ["BA", "CAT", "GE", "HON", "UNP", "UPS", "FDX", "LMT"]):
        return "Industrials"
    if any(k in pure_sym for k in ["NEE", "DUK", "SO", "AEP", "EXC", "XEL", "FTS", "EMA"]):
        return "Utilities"
    if any(k in pure_sym for k in ["PLD", "AMT", "CCI", "EQIX", "SPG", "O", "WELL"]):
        return "Real Estate"
    if any(k in pure_sym for k in ["T", "VZ", "TMUS", "CMCSA", "DIS", "NFLX"]):
        return "Communication Services"

    if "ETF" in n or "INDEX" in n:
        return "Index ETF"
    if "BOND" in n or "FIXED" in n or "INCOME" in n:
        return "Fixed Income / Bond"
    if "BANK" in n or "FINANCIAL" in n or "INSURANCE" in n:
        return "Financial Services"
    if "TECH" in n or "SOFTWARE" in n or "SEMICONDUCTOR" in n:
        return "Technology"
    if "ENERGY" in n or "OIL" in n or "GAS" in n:
        return "Energy"
    if "HEALTH" in n or "PHARMA" in n or "BIO" in n:
        return "Healthcare"

    return "Other / Diversified"


def calc_dividend_calendar(
    holdings: List[Dict[str, Any]],
    base_currency: str = "USD",
    fx_rates: Optional[Dict[str, float]] = None,
    months_ahead: int = 12,
    start_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Projects monthly dividend payout schedule across the upcoming months_ahead period."""
    if fx_rates is None:
        fx_rates = {}
    if start_date is None:
        start_date = datetime.now()

    month_labels = []
    y, m = start_date.year, start_date.month
    for _ in range(months_ahead):
        dt_repr = datetime(y, m, 1)
        month_labels.append(dt_repr.strftime("%b %Y"))
        m += 1
        if m > 12:
            m = 1
            y += 1

    monthly_totals = [0.0] * months_ahead
    holdings_breakdown = []

    for h in holdings:
        shares = float(h.get("shares", 0.0) or 0.0)
        ann_div = float(h.get("annual_dividend", 0.0) or 0.0)
        if shares <= 0 or ann_div <= 0:
            continue

        curr = str(h.get("currency", base_currency)).upper()
        rate = 1.0 if curr == base_currency.upper() else fx_rates.get(curr, 1.0)
        ann_div_base = ann_div * rate

        events = h.get("dividend_events") or []
        freq = calc_dividend_frequency(events)
        if freq == "None":
            sym = str(h.get("symbol", "")).upper()
            if "ZAG" in sym:
                freq = "Monthly"
            else:
                freq = "Quarterly"

        h_monthly = [0.0] * months_ahead
        if freq == "Monthly":
            payout = ann_div_base / 12.0
            for i in range(months_ahead):
                h_monthly[i] = round(payout, 2)
                monthly_totals[i] += payout
        elif freq == "Quarterly":
            payout = ann_div_base / 4.0
            for i in range(0, months_ahead, 3):
                h_monthly[i] = round(payout, 2)
                monthly_totals[i] += payout
        elif freq == "Semi-Annually":
            payout = ann_div_base / 2.0
            for i in range(0, months_ahead, 6):
                h_monthly[i] = round(payout, 2)
                monthly_totals[i] += payout
        else:
            payout = ann_div_base
            if months_ahead > 0:
                h_monthly[0] = round(payout, 2)
                monthly_totals[0] += payout

        holdings_breakdown.append({
            "symbol": h.get("symbol", ""),
            "name": h.get("name", ""),
            "frequency": freq,
            "annual_dividend_base": round(ann_div_base, 2),
            "monthly_schedule": h_monthly,
        })

    holdings_breakdown.sort(key=lambda x: x["annual_dividend_base"], reverse=True)
    monthly_totals = [round(t, 2) for t in monthly_totals]
    total_12m = round(sum(monthly_totals), 2)
    avg_monthly = round(total_12m / max(1, months_ahead), 2)

    schedule = []
    for i in range(months_ahead):
        payers = [hb["symbol"] for hb in holdings_breakdown if hb["monthly_schedule"][i] > 0]
        schedule.append({
            "month": month_labels[i],
            "cashflow": monthly_totals[i],
            "payers": payers
        })

    return {
        "months": month_labels,
        "monthly_totals": monthly_totals,
        "holdings_breakdown": holdings_breakdown,
        "schedule": schedule,
        "total_12m": total_12m,
        "annual_total": total_12m,
        "avg_monthly": avg_monthly,
    }


def calc_risk_and_return_metrics(
    price_or_val_series: List[float],
    timestamps: Optional[List[Any]] = None,
    risk_free_rate: float = 0.03,
) -> Dict[str, Any]:
    """Computes CAGR, Annualized Volatility, Sharpe Ratio, and Maximum Drawdown."""
    if not price_or_val_series or len(price_or_val_series) < 2:
        return {
            "cagr_pct": 0.0,
            "volatility_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
        }

    prices = [float(p) for p in price_or_val_series if float(p) > 0]
    if len(prices) < 2:
        return {
            "cagr_pct": 0.0,
            "volatility_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
        }

    daily_returns = []
    for i in range(1, len(prices)):
        p_prev = prices[i - 1]
        p_curr = prices[i]
        if p_prev > 0:
            daily_returns.append((p_curr - p_prev) / p_prev)

    if not daily_returns:
        return {
            "cagr_pct": 0.0,
            "volatility_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
        }

    mean_ret = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
    daily_vol = (variance ** 0.5)
    ann_vol = daily_vol * (252.0 ** 0.5)

    total_ret = (prices[-1] - prices[0]) / prices[0]
    years = (len(prices) / 252.0)
    if timestamps and len(timestamps) == len(price_or_val_series):
        try:
            t0, t1 = timestamps[0], timestamps[-1]
            if hasattr(t0, "timestamp") and hasattr(t1, "timestamp"):
                sec_diff = t1.timestamp() - t0.timestamp()
                if sec_diff > 86400:
                    years = sec_diff / (365.25 * 86400)
        except Exception:
            pass

    if years > 0 and (1.0 + total_ret) > 0:
        cagr = ((1.0 + total_ret) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr = total_ret * 100.0

    peak = prices[0]
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        if peak > 0:
            dd = (peak - p) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    rf_pct = risk_free_rate * 100.0
    ann_vol_pct = ann_vol * 100.0
    sharpe = ((cagr - rf_pct) / ann_vol_pct) if ann_vol_pct > 0 else 0.0

    return {
        "cagr_pct": round(cagr, 2),
        "volatility_pct": round(ann_vol_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
    }


def calc_tax_lot_proceeds(
    sale_shares: float,
    sale_price: float,
    buy_lots: List[Dict[str, Any]],
    method: str = "ACB",
) -> Dict[str, Any]:
    """Computes tax-lot proceeds, cost basis sold, and realized gain under ACB, FIFO, or SPECIFIC."""
    gross_proceeds = round(sale_shares * sale_price, 2)
    matched_lots = []
    cost_basis_sold = 0.0

    available_lots = []
    for lot in buy_lots:
        sh = float(lot.get("shares", 0.0))
        p = float(lot.get("buy_price") or lot.get("price") or 0.0)
        if sh > 0:
            available_lots.append({
                "date": lot.get("date", ""),
                "shares": sh,
                "price": p,
                "portfolio": lot.get("portfolio", ""),
                "symbol": lot.get("symbol", ""),
            })

    if method.upper() == "FIFO":
        available_lots.sort(key=lambda x: x.get("date", ""))
        needed_shares = sale_shares
        remaining_lots = []
        for lot in available_lots:
            if needed_shares <= 0:
                remaining_lots.append(lot)
                continue
            used = min(needed_shares, lot["shares"])
            matched_lots.append({
                "date": lot["date"],
                "shares_matched": used,
                "buy_price": lot["price"],
                "cost_basis": round(used * lot["price"], 2),
            })
            cost_basis_sold += used * lot["price"]
            needed_shares -= used
            if lot["shares"] > used:
                remaining_lots.append({
                    "date": lot["date"],
                    "shares": lot["shares"] - used,
                    "price": lot["price"],
                    "portfolio": lot.get("portfolio", ""),
                    "symbol": lot.get("symbol", ""),
                })
    elif method.upper() == "SPECIFIC":
        # Specific Identification (Highest Cost First)
        available_lots.sort(key=lambda x: x.get("price", 0.0), reverse=True)
        needed_shares = sale_shares
        remaining_lots = []
        for lot in available_lots:
            if needed_shares <= 0:
                remaining_lots.append(lot)
                continue
            used = min(needed_shares, lot["shares"])
            matched_lots.append({
                "date": lot["date"],
                "shares_matched": used,
                "buy_price": lot["price"],
                "cost_basis": round(used * lot["price"], 2),
            })
            cost_basis_sold += used * lot["price"]
            needed_shares -= used
            if lot["shares"] > used:
                remaining_lots.append({
                    "date": lot["date"],
                    "shares": lot["shares"] - used,
                    "price": lot["price"],
                    "portfolio": lot.get("portfolio", ""),
                    "symbol": lot.get("symbol", ""),
                })
    else:
        tot_shares = sum(l["shares"] for l in available_lots)
        tot_cost = sum(l["shares"] * l["price"] for l in available_lots)
        avg_cost_price = (tot_cost / tot_shares) if tot_shares > 0 else 0.0
        cost_basis_sold = sale_shares * avg_cost_price
        matched_lots.append({
            "method": "ACB",
            "shares_matched": sale_shares,
            "avg_cost_price": round(avg_cost_price, 4),
            "cost_basis": round(cost_basis_sold, 2),
        })
        rem_shares = max(0.0, tot_shares - sale_shares)
        remaining_lots = [{
            "shares": rem_shares,
            "price": avg_cost_price,
        }] if rem_shares > 0 else []

    cost_basis_sold = round(cost_basis_sold, 2)
    realized_gain = round(gross_proceeds - cost_basis_sold, 2)
    realized_roi = round((realized_gain / cost_basis_sold * 100.0), 2) if cost_basis_sold > 0 else 0.0

    return {
        "method": method.upper(),
        "sale_shares": sale_shares,
        "sale_price": sale_price,
        "gross_proceeds": gross_proceeds,
        "cost_basis_sold": cost_basis_sold,
        "realized_gain": realized_gain,
        "realized_roi_pct": realized_roi,
        "matched_lots": matched_lots,
        "remaining_lots": remaining_lots,
    }


def calc_dividend_frequency(dividend_events: List[Any]) -> str:
    """
    Infers the dividend payout frequency from a list of dividend events (tuples of (date, amount) or objects).
    Returns: 'Monthly', 'Quarterly', 'Semi-Annually', 'Annually', or 'Irregular' (or 'None' if empty).
    """
    if not dividend_events:
        return "None"

    pos_events = []
    for item in dividend_events:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            amt = float(item[1] or 0.0)
            if amt > 0:
                pos_events.append((item[0], amt))
        elif isinstance(item, dict):
            amt = float(item.get("amount", 0.0) or 0.0)
            dt = item.get("date") or item.get("timestamp")
            if amt > 0:
                pos_events.append((dt, amt))

    if not pos_events:
        return "None"

    # Count occurrences in the most recent 12-month active period if timestamps available
    try:
        ts_list = []
        for dt, _ in pos_events:
            if hasattr(dt, "timestamp"):
                ts_list.append(dt.timestamp())
            elif isinstance(dt, (int, float)):
                ts_list.append(float(dt))
        if ts_list:
            ts_list.sort()
            last_ts = ts_list[-1]
            events_1y = [ts for ts in ts_list if ts >= (last_ts - 365 * 86400)]
            cnt = len(events_1y)
            if cnt >= 10:
                return "Monthly"
            elif cnt in (3, 4, 5):
                return "Quarterly"
            elif cnt == 2:
                return "Semi-Annually"
            elif cnt == 1:
                return "Annually"
    except Exception:
        pass

    cnt = len(pos_events)
    if cnt >= 10:
        return "Monthly"
    elif 3 <= cnt <= 6:
        return "Quarterly"
    elif cnt == 2:
        return "Semi-Annually"
    elif cnt == 1:
        return "Annually"
    return "Irregular"


def parse_date_to_days_held(date_str: Optional[str]) -> Tuple[int, float]:
    """
    Parses a purchase date string and calculates elapsed days and years held from that date to today.
    Supports ISO formats (YYYY-MM-DD), timestamps, and colloquial dates (e.g. '7 May 2026').
    Returns:
        (days_held, years_held)
    """
    if not date_str:
        return 365, 1.0

    raw = str(date_str).strip()
    if not raw or raw in ("-", "N/A", "None", "nan"):
        return 365, 1.0

    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ]

    target_date = None
    for fmt in formats:
        try:
            target_date = datetime.strptime(raw, fmt).date()
            break
        except ValueError:
            continue

    if not target_date:
        # Try extracting YYYY-MM-DD substring if present
        import re
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw)
        if m:
            try:
                target_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

    if not target_date:
        return 365, 1.0

    today = date.today()
    delta_days = (today - target_date).days
    days_held = max(0, delta_days)
    years_held = round(days_held / 365.25, 4)
    return days_held, years_held


def calc_holding_earned_already(
    shares: float,
    buy_price: float,
    current_price: float,
    purchase_date_str: Optional[str] = None,
    annual_div_per_share: float = 0.0,
    div_yield: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculates stock earnings from purchase day till today:
    - Initial Cost Basis (Invested Capital)
    - Current Market Value
    - Capital Gain Earned Already ($ and %)
    - Holding Period (Days and Years)
    - Estimated Dividends Earned So Far ($)
    - Total Profit Earned Already ($ and % Total ROI)
    - Annualized Return (CAGR %)
    """
    shares = max(0.0, float(shares))
    buy_price = max(0.0, float(buy_price))
    current_price = max(0.0, float(current_price))

    cost_basis = round(shares * buy_price, 2)
    market_value = round(shares * current_price, 2)
    capital_gain = round(market_value - cost_basis, 2)
    capital_gain_pct = round((capital_gain / cost_basis * 100), 2) if cost_basis > 0 else 0.0

    days_held, years_held = parse_date_to_days_held(purchase_date_str)

    # Calculate dividend per share if missing but yield exists
    if annual_div_per_share <= 0.0 and div_yield > 0.0:
        annual_div_per_share = current_price * (div_yield / 100.0)

    past_dividends = round(shares * annual_div_per_share * years_held, 2) if years_held > 0 else 0.0
    total_earned_already = round(capital_gain + past_dividends, 2)
    total_roi_pct = round((total_earned_already / cost_basis * 100), 2) if cost_basis > 0 else 0.0

    # Compound Annual Growth Rate (CAGR)
    cagr_pct = 0.0
    if years_held >= 0.1 and cost_basis > 0 and (market_value + past_dividends) > 0:
        try:
            total_ratio = (market_value + past_dividends) / cost_basis
            cagr_pct = round(((total_ratio ** (1.0 / years_held)) - 1.0) * 100.0, 2)
        except (ValueError, OverflowError, ZeroDivisionError):
            cagr_pct = 0.0

    return {
        "shares": shares,
        "buy_price": buy_price,
        "current_price": current_price,
        "cost_basis": cost_basis,
        "market_value": market_value,
        "capital_gain": capital_gain,
        "capital_gain_pct": capital_gain_pct,
        "days_held": days_held,
        "years_held": years_held,
        "annual_div_per_share": round(annual_div_per_share, 4),
        "past_dividends": past_dividends,
        "total_earned_already": total_earned_already,
        "total_roi_pct": total_roi_pct,
        "cagr_pct": cagr_pct,
    }


def calc_future_dividend_milestones(
    shares: float,
    current_price: float,
    buy_price: float,
    div_yield_pct: float,
    annual_div_per_share: float = 0.0,
    div_growth_pct: float = 3.0,
    price_growth_pct: float = 6.0,
    monthly_contribution: float = 0.0,
    horizons: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Projects future dividend and capital growth across milestones (default 1, 3, 5, 10 years).
    Calculates:
    - How much you can earn from today till later
    - Total profit from purchase day through the future horizon
    - Cumulative dividend income and future position value
    """
    if horizons is None:
        horizons = [1, 3, 5, 10]

    max_yr = max(horizons) if horizons else 10
    history = calc_drip_simulation(
        initial_shares=shares,
        initial_price=current_price,
        div_yield_pct=div_yield_pct,
        div_growth_pct=div_growth_pct,
        price_growth_pct=price_growth_pct,
        monthly_contribution=monthly_contribution,
        years=max_yr,
    )

    initial_market_val = round(shares * current_price, 2)
    original_cost_basis = round(shares * buy_price, 2)

    milestones = {}
    cum_div = 0.0
    for row in history:
        yr = row["year"]
        cum_div += row["annual_dividend"]
        if yr in horizons:
            port_val = row["portfolio_value"]
            # New earnings gained from today forward
            new_profit_from_today = round(port_val - initial_market_val, 2)
            # Total profit from purchase day to future year
            total_profit_from_start = round(port_val - original_cost_basis, 2)
            roi_from_start = round((total_profit_from_start / original_cost_basis * 100), 2) if original_cost_basis > 0 else 0.0

            milestones[yr] = {
                "year": yr,
                "shares": row["shares"],
                "stock_price": row["stock_price"],
                "annual_dividend": row["annual_dividend"],
                "cumulative_dividends": round(cum_div, 2),
                "portfolio_value": port_val,
                "new_profit_from_today": new_profit_from_today,
                "total_profit_from_start": total_profit_from_start,
                "roi_from_start_pct": roi_from_start,
                "yield_on_cost": round((row["dividend_per_share"] / buy_price * 100), 2) if buy_price > 0 else 0.0,
            }

    return {
        "initial_cost_basis": original_cost_basis,
        "initial_market_value": initial_market_val,
        "milestones": milestones,
        "history": history,
    }


def calc_split_future_projections(
    shares: float,
    buy_price: float,
    current_price: float,
    ratio_from: float,
    ratio_to: float,
    purchase_date_str: Optional[str] = None,
    target_price: float = 0.0,
) -> Dict[str, Any]:
    """
    Computes stock performance from purchase day till today, the post-split position adjustments,
    and future growth milestones ('till later how much you can earn').
    """
    shares = max(0.0, float(shares))
    buy_price = max(0.0, float(buy_price))
    current_price = max(0.0, float(current_price))
    ratio_from = max(0.001, float(ratio_from))
    ratio_to = max(0.001, float(ratio_to))

    # 1. Earned already from purchase day till today
    cost_basis = round(shares * buy_price, 2)
    market_value = round(shares * current_price, 2)
    earned_already = round(market_value - cost_basis, 2)
    earned_already_pct = round((earned_already / cost_basis * 100), 2) if cost_basis > 0 else 0.0
    days_held, years_held = parse_date_to_days_held(purchase_date_str)

    # 2. Split adjustments
    multiplier = ratio_to / ratio_from
    new_shares = round(shares * multiplier, 4)
    new_buy_price = round(buy_price / multiplier, 4) if multiplier > 0 else buy_price
    new_current_price = round(current_price / multiplier, 4) if multiplier > 0 else current_price
    new_cost_basis = round(new_shares * new_buy_price, 2)
    new_market_value = round(new_shares * new_current_price, 2)

    # 3. Future Scenarios: Till later how much you can earn
    growth_rates = [10.0, 25.0, 50.0, 100.0]
    scenarios = []
    for g in growth_rates:
        p_fut = round(new_current_price * (1.0 + g / 100.0), 2)
        v_fut = round(new_shares * p_fut, 2)
        tot_prof = round(v_fut - cost_basis, 2)
        tot_roi = round((tot_prof / cost_basis * 100), 2) if cost_basis > 0 else 0.0
        new_prof = round(v_fut - market_value, 2)
        scenarios.append({
            "growth_pct": g,
            "future_price": p_fut,
            "future_value": v_fut,
            "total_profit_from_start": tot_prof,
            "total_roi_pct": tot_roi,
            "new_profit_from_today": new_prof,
        })

    # Pre-split price recovery scenario (reaching original un-split share price)
    recovery_value = round(new_shares * current_price, 2)
    recovery_total_profit = round(recovery_value - cost_basis, 2)
    recovery_new_profit = round(recovery_value - market_value, 2)
    recovery_roi = round((recovery_total_profit / cost_basis * 100), 2) if cost_basis > 0 else 0.0
    pre_split_recovery = {
        "target_price": current_price,
        "future_value": recovery_value,
        "total_profit_from_start": recovery_total_profit,
        "total_roi_pct": recovery_roi,
        "new_profit_from_today": recovery_new_profit,
    }

    # Custom target price scenario
    custom_target = None
    if target_price > 0:
        tgt_val = round(new_shares * target_price, 2)
        tgt_total_prof = round(tgt_val - cost_basis, 2)
        tgt_new_prof = round(tgt_val - market_value, 2)
        tgt_roi = round((tgt_total_prof / cost_basis * 100), 2) if cost_basis > 0 else 0.0
        custom_target = {
            "target_price": target_price,
            "future_value": tgt_val,
            "total_profit_from_start": tgt_total_prof,
            "total_roi_pct": tgt_roi,
            "new_profit_from_today": tgt_new_prof,
        }

    return {
        "original_shares": shares,
        "original_buy_price": buy_price,
        "original_current_price": current_price,
        "cost_basis": cost_basis,
        "market_value": market_value,
        "earned_already": earned_already,
        "earned_already_pct": earned_already_pct,
        "days_held": days_held,
        "years_held": years_held,
        "split_ratio": f"{ratio_to:g}:{ratio_from:g}",
        "multiplier": multiplier,
        "new_shares": new_shares,
        "new_buy_price": new_buy_price,
        "new_current_price": new_current_price,
        "new_cost_basis": new_cost_basis,
        "new_market_value": new_market_value,
        "scenarios": scenarios,
        "pre_split_recovery": pre_split_recovery,
        "custom_target": custom_target,
    }


def parse_tx_date(d_val: Any) -> Optional[date]:
    """
    Parses date string or date/datetime object into a datetime.date object.
    Supports ISO formats (YYYY-MM-DD, YYYY-MM-DD HH:MM:SS), colloquial dates (7 May 2026, May 7, 2026),
    and slash-separated formats (YYYY/MM/DD, DD/MM/YYYY).
    """
    if isinstance(d_val, datetime):
        return d_val.date()
    if isinstance(d_val, date):
        return d_val
    if not d_val or not isinstance(d_val, str):
        return None
    s = d_val.strip()
    if not s:
        return None

    # Try ISO YYYY-MM-DD pattern
    iso_match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%b-%Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Fallback attempt with regex for "day Month year"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m:
        for mfmt in ["%d %B %Y", "%d %b %Y"]:
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", mfmt).date()
            except ValueError:
                pass

    return None


def calc_period_earnings(
    transactions: List[Dict[str, Any]],
    period_mode: str = "this_month",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    portfolio_name: Optional[str] = None,
    today_override: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Calculates period earnings (realized profits, net ROI, cash flows) across transactions.
    Supported period modes:
    - 'this_week': From Monday of current week to Sunday of current week
    - 'this_month': From day 1 of current month to last day of current month
    - 'in_months': Groups all historical transactions by calendar month (YYYY-MM)
    - 'in_weeks': Groups all historical transactions by ISO week (YYYY-Www)
    - 'custom': Between start_date and end_date (inclusive)
    """
    now_date = today_override or date.today()

    # Determine date boundaries if applicable
    filter_start: Optional[date] = None
    filter_end: Optional[date] = None

    if period_mode == "this_week":
        filter_start = now_date - timedelta(days=now_date.weekday())
        filter_end = filter_start + timedelta(days=6)
    elif period_mode == "this_month":
        filter_start = date(now_date.year, now_date.month, 1)
        _, last_day = calendar.monthrange(now_date.year, now_date.month)
        filter_end = date(now_date.year, now_date.month, last_day)
    elif period_mode == "custom":
        filter_start = start_date
        filter_end = end_date

    # Filter transactions by portfolio and parsed date
    is_all_port = (
        not portfolio_name
        or portfolio_name in ("All Portfolios", "All", "*", "All Portfolios (Consolidated)")
        or "consolidated" in str(portfolio_name).lower()
    )

    parsed_txs = []
    for tx in transactions:
        p_name = tx.get("portfolio", "")
        if not is_all_port and p_name != portfolio_name:
            continue

        tx_date = parse_tx_date(tx.get("date"))
        if not tx_date:
            continue

        if filter_start and tx_date < filter_start:
            continue
        if filter_end and tx_date > filter_end:
            continue

        item = dict(tx)
        item["parsed_date"] = tx_date
        parsed_txs.append(item)

    # Sort descending by date
    parsed_txs.sort(key=lambda x: x["parsed_date"], reverse=True)

    def _summarize_group(tx_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        tot_prof = 0.0
        tot_cost = 0.0
        tot_sell_proceeds = 0.0
        tot_buy_volume = 0.0
        tot_dividend = 0.0
        tot_fees = 0.0
        buy_cnt = 0
        sell_cnt = 0
        div_cnt = 0
        fee_cnt = 0

        for t in tx_list:
            t_type = str(t.get("type", "")).upper()
            shares = float(t.get("shares", 0.0) or 0.0)
            net_amt = float(t.get("net_amount", t.get("net_proceeds", 0.0)) or 0.0)
            c_basis = float(t.get("cost_basis", 0.0) or 0.0)
            n_prof = float(t.get("net_profit", 0.0) or 0.0)
            tot_amt = float(t.get("total_amount", 0.0) or 0.0)

            if "SELL" in t_type:
                sell_cnt += 1
                tot_prof += n_prof
                tot_cost += c_basis
                tot_sell_proceeds += net_amt
            elif "BUY" in t_type:
                buy_cnt += 1
                tot_buy_volume += net_amt if net_amt > 0 else (c_basis if c_basis > 0 else (shares * float(t.get("price", 0.0) or 0.0)))
            elif "DIVIDEND" in t_type:
                div_cnt += 1
                div_val = n_prof if n_prof > 0 else net_amt
                tot_dividend += div_val
                tot_prof += div_val
            elif "FEE" in t_type or "STORAGE" in t_type or "CUSTODY" in t_type:
                fee_cnt += 1
                fee_val = abs(tot_amt) if tot_amt > 0 else (abs(net_amt) if net_amt > 0 else abs(n_prof))
                tot_fees += fee_val
                tot_prof -= fee_val

        roi_pct = round((tot_prof / tot_cost * 100), 2) if tot_cost > 0 else 0.0
        return {
            "total_realized_profit": round(tot_prof, 2),
            "total_cost_basis": round(tot_cost, 2),
            "total_sell_proceeds": round(tot_sell_proceeds, 2),
            "total_buy_volume": round(tot_buy_volume, 2),
            "total_dividend": round(tot_dividend, 2),
            "total_fees": round(tot_fees, 2),
            "net_roi_pct": roi_pct,
            "buy_count": buy_cnt,
            "sell_count": sell_cnt,
            "dividend_count": div_cnt,
            "fee_count": fee_cnt,
            "total_transactions": len(tx_list),
        }

    overall_summary = _summarize_group(parsed_txs)

    # Groupings for 'in_months' or 'in_weeks'
    breakdown = []
    if period_mode == "in_months":
        months_dict: Dict[str, List[Dict[str, Any]]] = {}
        for t in parsed_txs:
            m_key = t["parsed_date"].strftime("%Y-%m")
            if m_key not in months_dict:
                months_dict[m_key] = []
            months_dict[m_key].append(t)

        for m_key in sorted(months_dict.keys(), reverse=True):
            m_txs = months_dict[m_key]
            g_sum = _summarize_group(m_txs)
            breakdown.append({
                "period_label": m_key,
                **g_sum,
                "transactions": m_txs,
            })
    elif period_mode == "in_weeks":
        weeks_dict: Dict[str, List[Dict[str, Any]]] = {}
        week_ranges: Dict[str, Tuple[date, date]] = {}
        for t in parsed_txs:
            td = t["parsed_date"]
            iso_year, iso_week, _ = td.isocalendar()
            w_key = f"{iso_year}-W{iso_week:02d}"
            if w_key not in weeks_dict:
                weeks_dict[w_key] = []
                m_date = td - timedelta(days=td.weekday())
                s_date = m_date + timedelta(days=6)
                week_ranges[w_key] = (m_date, s_date)
            weeks_dict[w_key].append(t)

        for w_key in sorted(weeks_dict.keys(), reverse=True):
            w_txs = weeks_dict[w_key]
            m_date, s_date = week_ranges[w_key]
            g_sum = _summarize_group(w_txs)
            label = f"{w_key} ({m_date.strftime('%b %d')} - {s_date.strftime('%b %d')})"
            breakdown.append({
                "period_label": label,
                "start_date": m_date,
                "end_date": s_date,
                **g_sum,
                "transactions": w_txs,
            })

    return {
        "period_mode": period_mode,
        "portfolio": portfolio_name or "All Portfolios",
        "start_date": filter_start,
        "end_date": filter_end,
        "summary": overall_summary,
        "records": parsed_txs,
        "breakdown": breakdown,
    }


def calc_portfolio_rebalance(
    holdings: List[Dict[str, Any]],
    target_weights: Dict[str, float],
    new_cash: float = 0.0,
    mode: str = "full",
) -> Dict[str, Any]:
    """
    Computes portfolio rebalancing orders to match target allocation weights.
    mode: 'full' (allows buy & sell) or 'cash_only' (only buys using available new cash).
    """
    new_cash = max(0.0, float(new_cash))
    total_curr_val = 0.0
    items_map: Dict[str, Dict[str, Any]] = {}

    for h in holdings:
        sym = str(h.get("symbol", "")).strip().upper()
        if not sym:
            continue
        try:
            shares = float(h.get("shares", 0.0) or 0.0)
            price = float(h.get("current_price", 0.0) or h.get("price", 0.0) or 0.0)
        except (ValueError, TypeError):
            shares, price = 0.0, 0.0
        val = shares * price
        total_curr_val += val
        items_map[sym] = {
            "symbol": sym,
            "name": h.get("name", sym),
            "currency": h.get("currency", "USD"),
            "shares": shares,
            "price": price,
            "current_value": round(val, 2),
        }

    # Include any target symbols not currently held
    for sym in target_weights:
        s_clean = sym.strip().upper()
        if s_clean and s_clean not in items_map:
            items_map[s_clean] = {
                "symbol": s_clean,
                "name": s_clean,
                "currency": "USD",
                "shares": 0.0,
                "price": 0.0,
                "current_value": 0.0,
            }

    total_target_val = total_curr_val + new_cash
    sum_targets = sum(max(0.0, float(v)) for v in target_weights.values())
    norm_factor = (100.0 / sum_targets) if sum_targets > 0 else 1.0

    items_result = []
    used_cash = 0.0

    if mode == "cash_only":
        # Under cash-only mode, we prioritize buying the most underweight assets
        underweight_items = []
        for sym, d in items_map.items():
            curr_val = d["current_value"]
            curr_pct = (curr_val / total_curr_val * 100) if total_curr_val > 0 else 0.0
            tgt_pct = target_weights.get(sym, 0.0) * norm_factor
            ideal_val = total_target_val * (tgt_pct / 100.0)
            deficit = max(0.0, ideal_val - curr_val)
            underweight_items.append((sym, d, curr_pct, tgt_pct, ideal_val, deficit))

        tot_deficit = sum(it[5] for it in underweight_items)
        allocated_cash = 0.0

        for sym, d, curr_pct, tgt_pct, ideal_val, deficit in underweight_items:
            price = d["price"]
            if tot_deficit > 0 and new_cash > 0:
                share_cash = new_cash * (deficit / tot_deficit)
            else:
                share_cash = 0.0

            buy_shares = int(share_cash / price) if price > 0 else 0
            act_amount = round(buy_shares * price, 2)
            allocated_cash += act_amount

            items_result.append({
                "symbol": sym,
                "name": d["name"],
                "currency": d["currency"],
                "price": price,
                "current_shares": d["shares"],
                "current_value": d["current_value"],
                "current_weight_pct": round(curr_pct, 2),
                "target_weight_pct": round(tgt_pct, 2),
                "target_value": round(ideal_val, 2),
                "action": "BUY" if buy_shares > 0 else "HOLD",
                "shares_diff": buy_shares,
                "amount_diff": act_amount,
                "projected_shares": d["shares"] + buy_shares,
                "projected_value": round(d["current_value"] + act_amount, 2),
            })
        used_cash = allocated_cash
    else:
        # Full rebalancing: both BUY and SELL
        for sym, d in items_map.items():
            curr_val = d["current_value"]
            curr_pct = (curr_val / total_curr_val * 100) if total_curr_val > 0 else 0.0
            tgt_pct = target_weights.get(sym, 0.0) * norm_factor
            ideal_val = total_target_val * (tgt_pct / 100.0)
            diff_val = ideal_val - curr_val
            price = d["price"]

            if price > 0:
                shares_diff = int(diff_val / price)
                act_amount = round(abs(shares_diff) * price, 2)
            else:
                shares_diff = 0
                act_amount = 0.0

            action = "BUY" if shares_diff > 0 else ("SELL" if shares_diff < 0 else "HOLD")
            if action == "BUY":
                used_cash += act_amount
            elif action == "SELL":
                used_cash -= act_amount

            items_result.append({
                "symbol": sym,
                "name": d["name"],
                "currency": d["currency"],
                "price": price,
                "current_shares": d["shares"],
                "current_value": d["current_value"],
                "current_weight_pct": round(curr_pct, 2),
                "target_weight_pct": round(tgt_pct, 2),
                "target_value": round(ideal_val, 2),
                "action": action,
                "shares_diff": shares_diff,
                "amount_diff": act_amount,
                "projected_shares": d["shares"] + shares_diff,
                "projected_value": round(d["current_value"] + (shares_diff * price), 2),
            })

    # Filter out 0-share, 0-target, HOLD items (e.g. from deselected templates)
    items_result = [
        it for it in items_result
        if not (it["current_shares"] <= 0.0001 and it["target_weight_pct"] <= 0.0001 and it["action"] == "HOLD")
    ]

    items_result.sort(key=lambda x: (x["action"] != "BUY", x["action"] != "SELL", -x["target_weight_pct"]))

    return {
        "mode": mode,
        "total_current_value": round(total_curr_val, 2),
        "total_portfolio_value": round(total_curr_val, 2),
        "new_cash": round(new_cash, 2),
        "total_target_value": round(total_target_val, 2),
        "new_total_value": round(total_target_val, 2),
        "cash_allocated": round(used_cash, 2),
        "cash_remaining": round(max(0.0, new_cash - used_cash), 2),
        "items": items_result,
        "orders": items_result,
    }


def calc_bond_ladder_schedule(
    rle_annual: float,
    safe_years: float = 25.0,
    start_age: int = 60,
    current_safe_assets: float = 0.0,
    annual_inflation: float = 0.025,
) -> Dict[str, Any]:
    """
    Computes a 20-25 year liability-matching bond ladder schedule based on William J. Bernstein's
    framework ('The Four Pillars of Investing', Chapters 16-17).
    Matches year-by-year living expense liabilities with maturing TIPS or short Treasuries.
    """
    rle = max(0.0, float(rle_annual))
    years = max(1, min(40, int(round(safe_years))))
    cur_age = max(18, min(105, int(start_age)))
    cur_safe = max(0.0, float(current_safe_assets))
    inf = max(0.0, min(0.15, float(annual_inflation)))

    schedule = []
    cum_real = 0.0
    cum_nominal = 0.0
    remaining_safe = cur_safe

    for yr in range(1, years + 1):
        age_at_yr = cur_age + yr - 1
        inf_factor = (1.0 + inf) ** (yr - 1)
        nom_liability = round(rle * inf_factor, 2)
        real_liability = round(rle, 2)

        cum_real += real_liability
        cum_nominal += nom_liability

        # Funding status for this year
        if remaining_safe >= real_liability:
            funded_amt = real_liability
            remaining_safe -= real_liability
            status = "fully_funded"
        elif remaining_safe > 0:
            funded_amt = remaining_safe
            remaining_safe = 0.0
            status = "partially_funded"
        else:
            funded_amt = 0.0
            status = "unfunded"

        gap_amt = round(max(0.0, real_liability - funded_amt), 2)

        # Bernstein duration bucket & recommended ticker
        if yr <= 3:
            bucket_key = "cash_short_treasury"
            recommended_ticker = "VGSH / CASH.TO"
            instrument_type = "短期國債 / 高利現金"
        elif yr <= 8:
            bucket_key = "short_tips"
            recommended_ticker = "VTIP / XSB.TO"
            instrument_type = "短期 TIPS (0-5年)"
        else:
            bucket_key = "inter_tips"
            recommended_ticker = "TIP / LTPZ"
            instrument_type = "中長期 TIPS (7-20+年)"

        schedule.append({
            "year_index": yr,
            "age": age_at_yr,
            "real_liability": real_liability,
            "nominal_liability": nom_liability,
            "inflation_factor": round(inf_factor, 4),
            "funded_amount": round(funded_amt, 2),
            "gap_amount": gap_amt,
            "status": status,
            "bucket_key": bucket_key,
            "instrument_type": instrument_type,
            "recommended_ticker": recommended_ticker,
        })

    fully_funded_years = sum(1 for item in schedule if item["status"] == "fully_funded")
    fractional_years = round(min(float(years), cur_safe / rle), 1) if rle > 0 else float(years)
    total_real_needed = round(cum_real, 2)
    total_nominal_needed = round(cum_nominal, 2)
    overall_gap = round(max(0.0, total_real_needed - cur_safe), 2)
    overall_surplus = round(max(0.0, cur_safe - total_real_needed), 2)
    coverage_pct = round(min(500.0, (cur_safe / total_real_needed * 100.0)), 1) if total_real_needed > 0 else 100.0

    return {
        "schedule": schedule,
        "years": years,
        "start_age": cur_age,
        "end_age": cur_age + years - 1,
        "total_real_needed": total_real_needed,
        "total_nominal_needed": total_nominal_needed,
        "current_safe_assets": round(cur_safe, 2),
        "overall_gap": overall_gap,
        "overall_surplus": overall_surplus,
        "coverage_pct": coverage_pct,
        "fully_funded_years": fully_funded_years,
        "fractional_years": fractional_years,
        "annual_inflation": inf,
    }


def calc_pension_actuarial_comparison(
    base_annual_pension_at_65: float,
    current_age: int = 45,
    life_expectancy: int = 90,
) -> Dict[str, Any]:
    """
    Computes William J. Bernstein's actuarial delay-to-70 longevity insurance model
    ('The Four Pillars of Investing', Chapters 16-17).
    Compares claiming state pensions (Social Security / CPP / OAS) at ages 60, 65, and 70.
    """
    base_ann = max(0.0, float(base_annual_pension_at_65))
    life_exp = max(71, min(115, int(life_expectancy)))
    cur_age = max(18, min(100, int(current_age)))

    # Benefit multipliers relative to standard age 65
    mult_60 = 0.64   # Claim at 60 (-36% reduction: 5 yrs @ ~7.2%/yr penalty)
    mult_65 = 1.00   # Standard claim at 65 (100% baseline)
    mult_70 = 1.28   # Delayed claim at 70 (+28% permanent boost: 5 yrs @ ~8%/yr Bernstein credit)

    ann_60 = round(base_ann * mult_60, 2)
    ann_65 = round(base_ann * mult_65, 2)
    ann_70 = round(base_ann * mult_70, 2)

    mo_60 = round(ann_60 / 12.0, 2)
    mo_65 = round(ann_65 / 12.0, 2)
    mo_70 = round(ann_70 / 12.0, 2)

    # Calculate cumulative lifetime payouts across all ages up to 105
    yearly_trajectory = []
    cum_60 = 0.0
    cum_65 = 0.0
    cum_70 = 0.0

    be_65_vs_60 = None
    be_70_vs_65 = None
    be_70_vs_60 = None

    for age in range(60, 106):
        pay_60 = ann_60 if age >= 60 else 0.0
        pay_65 = ann_65 if age >= 65 else 0.0
        pay_70 = ann_70 if age >= 70 else 0.0

        cum_60 += pay_60
        cum_65 += pay_65
        cum_70 += pay_70

        if be_65_vs_60 is None and cum_65 >= cum_60 and age >= 65:
            be_65_vs_60 = age
        if be_70_vs_65 is None and cum_70 >= cum_65 and age >= 70:
            be_70_vs_65 = age
        if be_70_vs_60 is None and cum_70 >= cum_60 and age >= 70:
            be_70_vs_60 = age

        yearly_trajectory.append({
            "age": age,
            "pay_60": pay_60,
            "pay_65": pay_65,
            "pay_70": pay_70,
            "cum_60": round(cum_60, 2),
            "cum_65": round(cum_65, 2),
            "cum_70": round(cum_70, 2),
        })

    # Exact break-even interpolation if needed
    if be_70_vs_65 is None:
        be_70_vs_65 = 83  # Typical Bernstein break-even
    if be_65_vs_60 is None:
        be_65_vs_60 = 74

    # Milestone comparisons
    milestones = {}
    for m_age in [70, 75, 80, 85, 90, 95, 100]:
        row = next((r for r in yearly_trajectory if r["age"] == m_age), None)
        if row:
            milestones[m_age] = {
                "cum_60": row["cum_60"],
                "cum_65": row["cum_65"],
                "cum_70": row["cum_70"],
                "diff_70_vs_65": round(row["cum_70"] - row["cum_65"], 2),
                "diff_70_vs_60": round(row["cum_70"] - row["cum_60"], 2),
            }

    # Longevity gain at chosen life expectancy
    life_exp_row = next((r for r in yearly_trajectory if r["age"] == life_exp), yearly_trajectory[-1])
    gain_at_life_exp_vs_65 = round(life_exp_row["cum_70"] - life_exp_row["cum_65"], 2)
    gain_at_life_exp_vs_60 = round(life_exp_row["cum_70"] - life_exp_row["cum_60"], 2)

    return {
        "base_annual_at_65": base_ann,
        "base_monthly_at_65": mo_65,
        "claim_60": {
            "annual": ann_60,
            "monthly": mo_60,
            "multiplier": mult_60,
            "reduction_pct": 36.0,
        },
        "claim_65": {
            "annual": ann_65,
            "monthly": mo_65,
            "multiplier": mult_65,
            "reduction_pct": 0.0,
        },
        "claim_70": {
            "annual": ann_70,
            "monthly": mo_70,
            "multiplier": mult_70,
            "boost_pct": 28.0,
        },
        "breakeven_age_70_vs_65": be_70_vs_65,
        "breakeven_age_65_vs_60": be_65_vs_60,
        "breakeven_age_70_vs_60": be_70_vs_60 or 77,
        "life_expectancy": life_exp,
        "gain_at_life_exp_vs_65": gain_at_life_exp_vs_65,
        "gain_at_life_exp_vs_60": gain_at_life_exp_vs_60,
        "milestones": milestones,
        "yearly_trajectory": yearly_trajectory,
        "bernstein_pension_thesis": (
            "Bernstein Pension Principle: Delaying state pension to age 70 is the cheapest, "
            "highest-yielding CPI-indexed longevity insurance available in financial markets. "
            "For every year you survive past age 82, claiming at 70 produces accelerating lifetime surplus."
        ),
    }


def calc_deep_risk_diagnostic(
    holdings: Optional[List[Dict[str, Any]]] = None,
    safe_assets_val: float = 0.0,
    total_portfolio_val: float = 0.0,
    summary_currency: str = "USD",
) -> Dict[str, Any]:
    """
    Evaluates retirement portfolio resilience against William J. Bernstein's 
    'Four Deep Risks' (from Bernstein's treatise 'Deep Risk: How History Informs Portfolio Design'):
    1. Severe Inflation (持續性嚴重通膨): Destroys purchasing power of nominal fixed debt.
       - Hedges: TIPS (TIP, VTIP), short-term paper/cash (BIL, VGSH, CASH.TO), equity productive assets.
       - Vulnerabilities: Long-term nominal bonds (TLT, BND, AGG).
    2. Severe Deflation / Depression (嚴重通縮與大蕭條): Destroys equity earnings & corporate solvency.
       - Hedges: Sovereign high-grade government bonds (US Treasuries, TIPS), cash reserves.
       - Vulnerabilities: High equity concentration without safe buffer, leverage, junk debt.
    3. Confiscation / Expropriation (沒收、重稅與資本管制): Government financial repression / wealth confiscation.
       - Hedges: Multi-jurisdiction diversification, international assets (VXUS, VEA, foreign listings).
       - Vulnerabilities: 100% single-country local concentration.
    4. Devastation / Geopolitical Collapse (地緣毀滅與戰亂災難): Local physical/economic infrastructure collapse.
       - Hedges: Global equities across developed democracies, multinational revenue, hard currency.
       - Vulnerabilities: 100% domestic home bias in a single country.
    """
    if holdings is None:
        holdings = []

    safe_val = max(0.0, float(safe_assets_val))
    port_val = max(0.0, float(total_portfolio_val))
    sum_curr = str(summary_currency).upper()

    # Calculate portfolio values from holdings if total_portfolio_val not provided
    holding_total = 0.0
    intl_equity_val = 0.0
    tips_cash_val = 0.0
    nominal_long_bonds_val = 0.0
    equity_val = 0.0

    tips_tickers = {"TIP", "VTIP", "SCHP", "STIP", "SPIP"}
    cash_short_tickers = {"VGSH", "BIL", "SGOV", "SHV", "CASH.TO", "CASH", "PSA.TO", "GBIL"}
    nominal_long_tickers = {"TLT", "IEF", "BND", "AGG", "VGLT", "EDV", "ZROZ", "GOVT", "LQD", "HYG"}
    intl_tickers = {"VXUS", "VEA", "VWO", "EFA", "IXUS", "ACWI", "IEMG", "SCHF", "BNDX"}

    for h in holdings:
        sh = float(h.get("shares", 0.0) or 0.0)
        cp = float(h.get("current_price", 0.0) or 0.0)
        curr = str(h.get("currency", sum_curr)).upper()
        sym = str(h.get("symbol", "")).strip().upper()
        h_val = sh * cp
        holding_total += h_val

        # Asset classification checks
        is_intl = (
            curr != sum_curr
            or any(sym.startswith(t) or sym == t for t in intl_tickers)
            or sym.endswith(".HK")
            or sym.endswith(".TO")
            or sym.endswith(".L")
            or sym.endswith(".TW")
            or sym.endswith(".T")
            or "INTERNATIONAL" in str(h.get("name", "")).upper()
            or "EMERGING" in str(h.get("name", "")).upper()
            or "GLOBAL" in str(h.get("name", "")).upper()
        )
        if is_intl:
            intl_equity_val += h_val

        is_tips = any(sym.startswith(t) or sym == t for t in tips_tickers) or "TIPS" in str(h.get("name", "")).upper()
        is_cash_short = any(sym.startswith(t) or sym == t for t in cash_short_tickers) or "SHORT" in str(h.get("name", "")).upper()
        if is_tips or is_cash_short:
            tips_cash_val += h_val

        is_nom_long = any(sym.startswith(t) or sym == t for t in nominal_long_tickers)
        if is_nom_long:
            nominal_long_bonds_val += h_val

        if not (is_tips or is_cash_short or is_nom_long):
            equity_val += h_val

    effective_total = max(port_val, holding_total)
    if effective_total <= 0.0:
        effective_total = 1.0  # avoid zero division

    # Add explicit safe assets
    total_safe = max(safe_val, tips_cash_val)
    safe_ratio = min(1.0, total_safe / effective_total)
    intl_ratio = min(1.0, intl_equity_val / effective_total)
    equity_ratio = min(1.0, (equity_val + (effective_total - total_safe)) / effective_total)
    nominal_long_ratio = min(1.0, nominal_long_bonds_val / effective_total)

    # 1. Inflation Score (0 - 100)
    # TIPS, short duration cash, and productive equities hedge inflation; nominal long bonds hurt
    inf_score = 45.0
    if total_safe > 0:
        inf_score += min(30.0, (tips_cash_val / effective_total) * 100.0 * 1.5)
        # Having general safe assets helps if held in TIPS/short duration
        if tips_cash_val == 0 and safe_val > 0:
            inf_score += min(15.0, (safe_val / effective_total) * 50.0)
    if equity_ratio >= 0.40:
        inf_score += 25.0
    elif equity_ratio >= 0.20:
        inf_score += 15.0
    if nominal_long_ratio > 0.15:
        inf_score -= min(30.0, nominal_long_ratio * 100.0)
    inf_score = round(max(10.0, min(100.0, inf_score)), 1)

    # 2. Deflation / Depression Score (0 - 100)
    # Sovereign safe assets and liquidity protect against debt deflation and corporate insolvencies
    if safe_ratio >= 0.35:
        def_score = 95.0
    elif safe_ratio >= 0.25:
        def_score = 85.0
    elif safe_ratio >= 0.15:
        def_score = 70.0
    elif safe_ratio >= 0.05:
        def_score = 55.0
    else:
        def_score = 35.0  # High deflation vulnerability if 100% equity
    def_score = round(max(10.0, min(100.0, def_score)), 1)

    # 3. Confiscation / Expropriation Score (0 - 100)
    # Multi-jurisdiction diversification vs 100% domestic risk
    if intl_ratio >= 0.30:
        conf_score = 92.0
    elif intl_ratio >= 0.20:
        conf_score = 82.0
    elif intl_ratio >= 0.10:
        conf_score = 68.0
    elif intl_ratio > 0.02:
        conf_score = 55.0
    else:
        conf_score = 40.0  # 100% single-country concentration
    conf_score = round(max(10.0, min(100.0, conf_score)), 1)

    # 4. Devastation / Geopolitical Collapse Score (0 - 100)
    # Global economic equity diversification ensures survival against local war/collapse
    if intl_ratio >= 0.25 and equity_ratio >= 0.30:
        dev_score = 90.0
    elif intl_ratio >= 0.10:
        dev_score = 75.0
    elif equity_ratio >= 0.50:
        # High equity with global multinational exposure
        dev_score = 65.0
    else:
        dev_score = 45.0
    dev_score = round(max(10.0, min(100.0, dev_score)), 1)

    # Composite Score & Grade
    overall_score = round((inf_score + def_score + conf_score + dev_score) / 4.0, 1)
    if overall_score >= 85.0:
        grade = "A"
        grade_desc = "Fortified Defense (磐石防禦)"
    elif overall_score >= 70.0:
        grade = "B"
        grade_desc = "Resilient Baseline (穩健平衡)"
    elif overall_score >= 50.0:
        grade = "C"
        grade_desc = "Moderate Vulnerability (存在漏洞)"
    else:
        grade = "D"
        grade_desc = "Critical Deep Risk Exposure (高危暴露)"

    strengths = []
    weaknesses = []
    recommendations = []

    if inf_score >= 75.0:
        strengths.append("High inflation resilience supported by TIPS / cash-flow productive equities.")
    else:
        weaknesses.append("Vulnerable to double-digit inflation if holding long nominal bonds or low TIPS.")
        recommendations.append({
            "risk": "Severe Inflation",
            "action": "Allocate 15-20% into TIPS (TIP/VTIP) or ultra-short government debt (VGSH). Avoid 10+ year nominal bonds.",
        })

    if def_score >= 75.0:
        strengths.append("Sufficient sovereign safe asset buffer (>25%) to survive deep multi-year depression.")
    else:
        weaknesses.append("Safe asset buffer is below 20%, exposing portfolio to forced equity liquidation in severe deflation.")
        recommendations.append({
            "risk": "Severe Deflation",
            "action": "Build 20-25 years of residual living expenses in sovereign bonds / TIPS ladder to eliminate sequence risk.",
        })

    if conf_score >= 75.0:
        strengths.append("Broad multi-jurisdiction and global currency exposure hedges localized capital controls.")
    else:
        weaknesses.append("Heavy domestic concentration exposes capital to local fiscal repression or punitive taxation.")
        recommendations.append({
            "risk": "Confiscation",
            "action": "Hold 20-35% in international ex-domestic equities (e.g. VXUS, VEA) or multi-jurisdictional assets.",
        })

    if dev_score >= 75.0:
        strengths.append("Global equity diversification insulates capital against regional geopolitical collapse.")
    else:
        weaknesses.append("Lack of global geographic diversification increases vulnerability to regional geopolitical shocks.")
        recommendations.append({
            "risk": "Devastation",
            "action": "Maintain global market allocation across North America, Europe, and Asia-Pacific.",
        })

    return {
        "overall_score": overall_score,
        "overall_grade": grade,
        "grade_desc": grade_desc,
        "inflation_score": inf_score,
        "deflation_score": def_score,
        "confiscation_score": conf_score,
        "devastation_score": dev_score,
        "safe_ratio_pct": round(safe_ratio * 100.0, 1),
        "intl_ratio_pct": round(intl_ratio * 100.0, 1),
        "equity_ratio_pct": round(equity_ratio * 100.0, 1),
        "nominal_long_ratio_pct": round(nominal_long_ratio * 100.0, 1),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": recommendations,
        "bernstein_thesis": (
            "William J. Bernstein 'Deep Risk' Thesis: Shallow risk is temporary market volatility (which patient "
            "investors can ignore). Deep risk is permanent loss of real capital through Inflation, Deflation, "
            "Confiscation, or Devastation. A truly antifragile retirement portfolio must immunize against all four."
        ),
    }


def calc_historical_crisis_stress_test(
    portfolio_val: float,
    rle_annual: float,
    safe_assets_val: float = 0.0,
    safe_years: float = 25.0,
) -> Dict[str, Any]:
    """
    Simulates sequence-of-returns stress testing across the 4 most catastrophic historical crises:
    1. 1929 Great Crash & Depression: -86% real equity drawdown.
    2. 1973–1974 Stagflation: -48% real equity crash + 12% double-digit inflation.
    3. 2000–2002 Dot-Com Crash & 'Lost Decade': -49% S&P 500 across 3 consecutive down years.
    4. 2008 Global Financial Crisis: -57% equity plunge with systemic liquidity freeze.

    Contrasts:
    - Scenario A (Unhedged): Living expenses liquidated directly from equity portfolio at market bottoms.
    - Scenario B (Bernstein Dual-Engine): Living expenses 100% drawn from safe bond ladder; equities left to rebound untouched.
    """
    port = max(0.0, float(portfolio_val))
    rle = max(0.0, float(rle_annual))
    safe_val = max(0.0, float(safe_assets_val))

    # Define historical 10-year real return & inflation sequences
    crises_specs = {
        "1929": {
            "name": "1929 Great Depression (大蕭條極端考驗)",
            "desc": "Wall Street Crash of 1929 followed by 4 years of severe economic contraction (-86% real drawdown).",
            "stock_returns": [-0.119, -0.285, -0.438, -0.086, 0.540, -0.014, 0.477, 0.339, -0.350, 0.311],
            "inflation_rates": [-0.02, -0.09, -0.10, -0.05, 0.01, 0.03, 0.02, 0.01, 0.04, -0.02],
        },
        "1973": {
            "name": "1973-1974 Stagflation Crisis (停滯性通膨風暴)",
            "desc": "OPEC oil shock causing 12% double-digit inflation combined with -48% real equity drawdown.",
            "stock_returns": [-0.182, -0.297, 0.290, 0.180, -0.123, 0.004, 0.048, 0.170, -0.100, 0.148],
            "inflation_rates": [0.088, 0.122, 0.070, 0.048, 0.068, 0.090, 0.133, 0.125, 0.089, 0.038],
        },
        "2000": {
            "name": "2000 Dot-Com Crash & Lost Decade (科技泡沫與失落十年)",
            "desc": "Three consecutive down years in S&P 500 (-49% total) culminating in the 2008 subprime crisis.",
            "stock_returns": [-0.091, -0.119, -0.221, 0.287, 0.109, 0.049, 0.158, 0.055, -0.370, 0.265],
            "inflation_rates": [0.034, 0.028, 0.016, 0.023, 0.027, 0.034, 0.032, 0.028, 0.038, -0.004],
        },
        "2008": {
            "name": "2008 Global Financial Crisis (全球金融海嘯)",
            "desc": "Subprime mortgage collapse (-57% equity peak-to-trough) followed by prolonged quantitative easing recovery.",
            "stock_returns": [-0.370, 0.265, 0.151, 0.021, 0.160, 0.324, 0.137, 0.014, 0.120, 0.218],
            "inflation_rates": [0.038, -0.004, 0.016, 0.032, 0.021, 0.015, 0.016, 0.001, 0.013, 0.021],
        },
    }

    # If user has no safe assets allocated, simulate Bernstein's recommended 10-year liability matching buffer
    model_safe_buffer = safe_val if safe_val > 0 else min(port * 0.40, rle * 10.0)

    results_by_crisis = {}
    aggregate_preserved_capital = 0.0

    for key, spec in crises_specs.items():
        stock_rets = spec["stock_returns"]
        inf_rates = spec["inflation_rates"]

        unhedged_wealth = port
        unhedged_history = []
        hedged_equity = max(0.0, port - model_safe_buffer)
        hedged_safe = model_safe_buffer
        hedged_history = []

        curr_expense = rle

        for year_idx in range(10):
            year_num = year_idx + 1
            ret = stock_rets[year_idx]
            inf = inf_rates[year_idx]

            # Adjust expense with historical crisis inflation
            curr_expense = curr_expense * (1.0 + inf)

            # Scenario A: Unhedged liquidation
            # Expense deducted at start of year, remainder experiences stock return
            unhedged_start = unhedged_wealth
            unhedged_post_draw = max(0.0, unhedged_start - curr_expense)
            unhedged_end = round(unhedged_post_draw * (1.0 + ret), 2)
            unhedged_wealth = max(0.0, unhedged_end)
            unhedged_history.append({
                "year": year_num,
                "withdrawal": round(curr_expense, 2),
                "stock_return_pct": round(ret * 100.0, 1),
                "ending_wealth": unhedged_wealth,
            })

            # Scenario B: Bernstein Hedged
            # Expense drawn from safe buffer first; safe buffer earns TIPS real yield ~1.5%
            draw_from_safe = min(hedged_safe, curr_expense)
            remaining_draw = max(0.0, curr_expense - draw_from_safe)
            hedged_safe = max(0.0, (hedged_safe - draw_from_safe) * 1.015)

            # Equities only liquidated if safe buffer completely exhausted
            hedged_equity_post_draw = max(0.0, hedged_equity - remaining_draw)
            hedged_equity = round(hedged_equity_post_draw * (1.0 + ret), 2)
            hedged_total = round(hedged_equity + hedged_safe, 2)

            hedged_history.append({
                "year": year_num,
                "withdrawal": round(curr_expense, 2),
                "safe_drawn": round(draw_from_safe, 2),
                "safe_remaining": round(hedged_safe, 2),
                "equity_remaining": round(hedged_equity, 2),
                "ending_wealth": hedged_total,
            })

        terminal_unhedged = unhedged_wealth
        terminal_hedged = hedged_total
        capital_preserved = round(terminal_hedged - terminal_unhedged, 2)
        aggregate_preserved_capital += capital_preserved

        # Survival evaluation
        ruin_in_unhedged = any(h["ending_wealth"] <= 0 for h in unhedged_history)
        preservation_pct = round((terminal_hedged / max(1.0, port)) * 100.0, 1)

        results_by_crisis[key] = {
            "name": spec["name"],
            "desc": spec["desc"],
            "terminal_unhedged": terminal_unhedged,
            "terminal_hedged": terminal_hedged,
            "capital_preserved": capital_preserved,
            "capital_preserved_ratio": round(terminal_hedged / max(1.0, terminal_unhedged), 2) if terminal_unhedged > 0 else 99.9,
            "wealth_preservation_pct": preservation_pct,
            "ruin_in_unhedged": ruin_in_unhedged,
            "unhedged_history": unhedged_history,
            "hedged_history": hedged_history,
        }

    return {
        "portfolio_initial": port,
        "rle_annual": rle,
        "safe_buffer_used": round(model_safe_buffer, 2),
        "results_by_crisis": results_by_crisis,
        "avg_capital_preserved": round(aggregate_preserved_capital / len(crises_specs), 2),
        "bernstein_stress_thesis": (
            "William J. Bernstein Sequence-of-Returns Law: Market crashes don't kill retirees; forced liquidation "
            "at market bottoms does. With a 10 to 25-year safe bond buffer (TIPS/Treasuries), your living expenses "
            "are completely decoupled from equity prices, allowing depressed equities to rebound unimpaired."
        ),
    }


def calc_cape_dynamic_swr(
    current_cape: float = 34.0,
    base_swr: float = 0.032,
    portfolio_val: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculates Shiller CAPE-adjusted Dynamic Safe Withdrawal Rate (SWR) corridor (2.0% - 3.8%)
    based on William J. Bernstein's valuation framework ('The Four Pillars of Investing', Ch 6):
    - Historical median S&P 500 Shiller CAPE ~ 16.5.
    - When CAPE is extreme (>30), subsequent 10-15 year equity real returns are depressed (~3-4%).
    - Dynamic SWR = clamp(2.0%, 3.8%, Base SWR * (1 + (16.5 - Current CAPE) / 60.0)).
    """
    cape = max(5.0, min(80.0, float(current_cape)))
    base = max(0.02, min(0.05, float(base_swr)))
    port = max(0.0, float(portfolio_val))

    # Dynamic formula
    scale = (16.5 - cape) / 60.0
    dynamic_rate_pct = round(max(2.0, min(3.8, base * 100.0 * (1.0 + scale))), 2)
    dynamic_swr = dynamic_rate_pct / 100.0

    annual_withdrawal_cap = round(port * dynamic_swr, 2)
    monthly_withdrawal_cap = round(annual_withdrawal_cap / 12.0, 2)

    # Static 4% comparison
    static_4pct_annual = round(port * 0.04, 2)
    static_4pct_monthly = round(static_4pct_annual / 12.0, 2)
    annual_withdrawal_delta = round(annual_withdrawal_cap - static_4pct_annual, 2)

    if cape >= 33.0:
        zone = "extreme_bubble"
        zone_name = "Extreme High Valuation / Bubble Risk (極高估值/泡沫預警區)"
        color = "#c5221f"
        guidance = (
            f"Current CAPE ({cape:.1f}) is in the top 5% of historical market valuations. Future 10-15 year "
            f"equity real returns are expected to compress to 3%-4%. Bernstein recommends capping SWR at "
            f"{dynamic_rate_pct}% to avoid catastrophic sequence-of-returns impairment."
        )
    elif cape >= 25.0:
        zone = "elevated"
        zone_name = "Elevated Valuation (偏高估值區)"
        color = "#e37400"
        guidance = (
            f"Current CAPE ({cape:.1f}) is elevated above historical normal. Recommended SWR is "
            f"{dynamic_rate_pct}%. Keep discretionary spending flexible and prioritize safe asset reserves."
        )
    elif cape >= 16.0:
        zone = "fair"
        zone_name = "Historical Fair Valuation (合理估值區)"
        color = "#137333"
        guidance = (
            f"Current CAPE ({cape:.1f}) is aligned with historical median (~16.5). Standard baseline SWR "
            f"of {dynamic_rate_pct}% offers robust safety across retirement horizons."
        )
    else:
        zone = "bargain"
        zone_name = "Undervalued / High Safety Cushion (低估/高安全邊際區)"
        color = "#1a73e8"
        guidance = (
            f"Current CAPE ({cape:.1f}) is deeply depressed, offering high forward expected returns. "
            f"Safe withdrawal capacity comfortably expands up to {dynamic_rate_pct}%."
        )

    return {
        "current_cape": cape,
        "historical_median_cape": 16.5,
        "base_swr_pct": round(base * 100.0, 2),
        "dynamic_swr_pct": dynamic_rate_pct,
        "dynamic_swr_decimal": dynamic_swr,
        "annual_withdrawal_cap": annual_withdrawal_cap,
        "monthly_withdrawal_cap": monthly_withdrawal_cap,
        "static_4pct_annual": static_4pct_annual,
        "static_4pct_monthly": static_4pct_monthly,
        "annual_withdrawal_delta": annual_withdrawal_delta,
        "zone": zone,
        "zone_name": zone_name,
        "zone_color": color,
        "guidance": guidance,
        "bernstein_quote": (
            "William J. Bernstein: 'The 4% rule was derived from a historical period when real bond yields were 2-3% "
            "and equities started from low valuations. When market valuations (CAPE) are at historic peaks, starting "
            "with a static 4% withdrawal invites disaster. Adjust your spending down to 2-3% during bubble regimes.'"
        ),
    }


# -------------------------------------------------------------------------
# Phase 3: Bernstein Friction & Optimization Engines
# -------------------------------------------------------------------------

KNOWN_ETF_TER: Dict[str, float] = {
    "VOO": 0.03, "VTI": 0.03, "IVV": 0.03, "SPY": 0.09, "QQQ": 0.20,
    "SCHD": 0.06, "VXUS": 0.08, "VEA": 0.06, "VWO": 0.08, "VT": 0.07,
    "BND": 0.03, "AGG": 0.03, "TIP": 0.19, "VTIP": 0.04, "VGSH": 0.04,
    "GLD": 0.40, "VNQ": 0.13, "VFV": 0.09, "XEQT": 0.20, "VEQT": 0.24,
    "VGRO": 0.24, "XGRO": 0.20, "VBAL": 0.24, "XEF": 0.22, "VDY": 0.22,
    "XIU": 0.18, "ZAG": 0.09, "XSB": 0.10, "CASH": 0.11, "BIL": 0.14,
    "SGOV": 0.07, "SHV": 0.15, "AVUV": 0.25, "AVDV": 0.36, "VBR": 0.07,
    "CSPX": 0.07, "VUAA": 0.07, "VWRA": 0.22, "SWRD": 0.12, "EUNL": 0.20,
}


def calc_fee_and_tax_drag_autopsy(
    holdings: Optional[List[Dict[str, Any]]] = None,
    portfolio_val: float = 0.0,
    investor_region: str = "CA",  # "CA" (Canada), "US" (USA), "INTL" (Non-Treaty), "HK_TW" (0% CGT)
    account_type: str = "taxable",  # "taxable", "tfsa", "rrsp", "roth"
    nominal_gross_return: float = 0.075,  # 7.5% nominal gross return
    dividend_yield_pct: float = 2.0,  # 2.0% dividend yield
    annual_turnover_pct: float = 10.0,  # 10% annual portfolio turnover / rebalancing realization
    custom_cgt_rate_pct: Optional[float] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Computes William J. Bernstein's 30-Year Fee & Tax Friction Compounding Drag Autopsy
    ('The Four Pillars of Investing', Pillar 4: 'Where Are the Customers' Yachts?').
    """
    if holdings is None:
        holdings = []

    if portfolio_val <= 0.0 and "portfolio_initial" in kwargs:
        portfolio_val = float(kwargs["portfolio_initial"])

    investor_region = kwargs.get("region", kwargs.get("tax_region", investor_region))
    account_type = kwargs.get("account_type", account_type)

    port_val = max(0.0, float(portfolio_val))
    reg_raw = str(investor_region).upper().strip()
    if any(k in reg_raw for k in ("CAN", "CA")):
        reg = "CA"
    elif any(k in reg_raw for k in ("NON", "INTL", "HK", "TW", "SG", "ASIA")):
        reg = "INTL"
    elif "US" in reg_raw:
        reg = "US"
    else:
        reg = "CA"

    acct_raw = str(account_type).lower().strip()
    if "rrsp" in acct_raw or "rrif" in acct_raw:
        acct = "rrsp"
    elif "tfsa" in acct_raw:
        acct = "tfsa"
    elif "roth" in acct_raw or "401" in acct_raw:
        acct = "roth"
    else:
        acct = "taxable"

    gross_ret = max(0.01, min(0.20, float(nominal_gross_return)))
    div_yield = max(0.0, min(0.15, float(dividend_yield_pct)))
    turnover = max(0.0, min(1.0, float(annual_turnover_pct) / 100.0))

    # Calculate holding-level weights and values
    total_val = 0.0
    holding_details = []

    for h in holdings:
        sh = float(h.get("shares", 0.0) or 0.0)
        p = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
        h_val = max(0.0, sh * p)
        total_val += h_val

    effective_port_val = max(port_val, total_val)
    if effective_port_val <= 0.0:
        effective_port_val = 100000.0  # default modeling base

    weighted_ter = 0.0
    weighted_wht = 0.0

    for h in holdings:
        sh = float(h.get("shares", 0.0) or 0.0)
        p = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
        h_val = max(0.0, sh * p)
        w = (h_val / effective_port_val) if effective_port_val > 0 else 0.0

        raw_sym = str(h.get("symbol", "")).strip().upper()
        clean_sym = raw_sym.split(":")[0].split(".")[0].strip()
        curr = str(h.get("currency", "USD")).upper()

        # 1. Determine Expense Ratio (TER / MER)
        if clean_sym in KNOWN_ETF_TER:
            ter = KNOWN_ETF_TER[clean_sym]
        elif "expense_ratio" in h and h["expense_ratio"] is not None:
            ter = float(h["expense_ratio"])
        elif "mer" in h and h["mer"] is not None:
            ter = float(h["mer"])
        else:
            # Check if it looks like an ETF or mutual fund
            name = str(h.get("name", "")).upper()
            if "ETF" in name or "INDEX" in name or "FUND" in name or clean_sym in ("XEQT", "VGRO", "VFV", "VEQT"):
                ter = 0.18
            else:
                ter = 0.0  # Individual stock has 0% fund expense ratio

        # 2. Determine Dividend Withholding Tax (WHT)
        is_us_asset = curr == "USD" or clean_sym in ("VOO", "VTI", "SPY", "QQQ", "SCHD", "IVV", "TIP", "VGSH", "VT")
        is_cad_asset = curr == "CAD" or raw_sym.endswith(":TSE") or raw_sym.endswith(".TO")
        is_hk_uk_asset = curr in ("HKD", "GBP") or raw_sym.endswith(".HK") or raw_sym.endswith(".L")

        if is_us_asset:
            if reg == "CA":
                if acct == "rrsp":
                    wht = 0.0  # Article XXI US-Canada Treaty exemption
                else:
                    wht = 15.0  # Treaty rate with W-8BEN (TFSA or Taxable)
            elif reg == "US" or acct == "roth":
                wht = 0.0  # Domestic IRS rules
            elif reg in ("INTL", "HK_TW", "TW", "HK", "SG"):
                wht = 30.0  # Non-treaty statutory WHT on US-domiciled equities
            else:
                wht = 15.0
        elif is_cad_asset:
            if reg == "CA":
                wht = 0.0  # Canadian eligible dividend tax credit applies
            else:
                wht = 15.0  # Non-resident withholding tax
        elif is_hk_uk_asset:
            wht = 0.0  # Hong Kong & UK have 0% dividend withholding tax
        else:
            wht = 15.0 if reg == "CA" else (30.0 if reg == "INTL" else 0.0)

        weighted_ter += w * ter
        weighted_wht += w * wht

        holding_details.append({
            "symbol": raw_sym,
            "name": h.get("name", raw_sym),
            "weight_pct": round(w * 100.0, 1),
            "ter_pct": ter,
            "wht_pct": wht,
        })

    # If no holdings passed, use reasonable defaults based on region
    if not holdings or total_val <= 0:
        weighted_ter = 0.15
        if reg == "CA":
            weighted_wht = 0.0 if acct == "rrsp" else 15.0
        elif reg == "US":
            weighted_wht = 0.0
        else:
            weighted_wht = 30.0

    # 3. Capital Gains Tax (CGT) rate
    if custom_cgt_rate_pct is not None:
        effective_cgt_pct = max(0.0, float(custom_cgt_rate_pct))
    else:
        if acct in ("tfsa", "roth"):
            effective_cgt_pct = 0.0
        elif acct == "rrsp":
            effective_cgt_pct = 0.0  # Tax-deferred during growth
        elif acct == "taxable":
            if reg == "CA":
                effective_cgt_pct = 19.0  # 50% inclusion * ~38% marginal
            elif reg == "US":
                effective_cgt_pct = 15.0  # Federal long-term CGT
            elif reg in ("INTL", "HK_TW", "HK", "TW", "SG"):
                effective_cgt_pct = 0.0   # 0% capital gains tax
            else:
                effective_cgt_pct = 15.0
        else:
            effective_cgt_pct = 0.0

    # 4. Annualized Frictions
    # Dividend Drag % = (Dividend Yield %) * (WHT % / 100)
    annual_div_drag_pct = round((div_yield * (weighted_wht / 100.0)), 3)
    # CGT Drag % = Capital appreciation * annual turnover * CGT rate
    capital_growth_portion = max(0.0, gross_ret - (div_yield / 100.0))
    annual_cgt_drag_pct = round(capital_growth_portion * turnover * (effective_cgt_pct / 100.0) * 100.0, 3)

    total_annual_friction_pct = round(weighted_ter + annual_div_drag_pct + annual_cgt_drag_pct, 3)

    # Benchmark: Bernstein Low-Cost & Tax-Optimized Portfolio
    benchmark_ter = 0.04
    benchmark_wht = 0.0 if (reg == "US" or acct == "rrsp") else (15.0 if reg == "CA" else 15.0)  # via Ireland UCITS or treaty
    benchmark_div_drag_pct = (div_yield * (benchmark_wht / 100.0))
    benchmark_cgt_drag_pct = capital_growth_portion * 0.02 * (effective_cgt_pct / 100.0) * 100.0  # ultra-low turnover
    benchmark_total_friction_pct = round(benchmark_ter + benchmark_div_drag_pct + benchmark_cgt_drag_pct, 3)

    # 5. Multi-Decade Compounding Projections (Year 1 to 30)
    net_ret_gross = gross_ret
    net_ret_bench = max(0.0, gross_ret - (benchmark_total_friction_pct / 100.0))
    net_ret_port = max(0.0, gross_ret - (total_annual_friction_pct / 100.0))

    history_10_20_30 = {}
    trajectory = []

    g_val = effective_port_val
    b_val = effective_port_val
    p_val = effective_port_val

    for yr in range(1, 31):
        g_val = round(g_val * (1.0 + net_ret_gross), 2)
        b_val = round(b_val * (1.0 + net_ret_bench), 2)
        p_val = round(p_val * (1.0 + net_ret_port), 2)

        lost_to_frictions = round(g_val - p_val, 2)
        pct_lost = round((lost_to_frictions / max(1.0, g_val)) * 100.0, 1)

        point = {
            "year": yr,
            "gross_wealth": g_val,
            "benchmark_wealth": b_val,
            "portfolio_wealth": p_val,
            "dollars_lost": lost_to_frictions,
            "pct_wealth_lost": pct_lost,
            "total_drag": lost_to_frictions,
            "drag_pct": pct_lost,
        }
        trajectory.append(point)

        if yr in (10, 20, 30):
            fee_dollars_lost = round(g_val - (effective_port_val * ((1.0 + gross_ret - (weighted_ter / 100.0)) ** yr)), 2)
            tax_dollars_lost = round(max(0.0, lost_to_frictions - fee_dollars_lost), 2)
            history_10_20_30[yr] = {
                "gross_wealth": g_val,
                "benchmark_wealth": b_val,
                "portfolio_wealth": p_val,
                "total_lost": lost_to_frictions,
                "fee_lost": fee_dollars_lost,
                "tax_lost": tax_dollars_lost,
                "pct_lost": pct_lost,
                "delta_vs_benchmark": round(b_val - p_val, 2),
            }

    # 6. Bernstein Tax & Fee Prescriptions
    recommendations = []
    if reg == "CA":
        if acct != "rrsp":
            recommendations.append({
                "category": "Tax Treaty Asset Location",
                "tip": "Move US dividend-paying ETFs (VOO, SCHD) into an RRSP/RRIF. Under Article XXI of the US-Canada Tax Treaty, US dividend withholding tax drops from 15% to 0%, saving thousands in annual drag.",
            })
        if acct == "tfsa":
            recommendations.append({
                "category": "TFSA Leakage Prevention",
                "tip": "The 15% US withholding tax inside a TFSA cannot be recovered via Foreign Tax Credit. Prefer Canadian all-in-one equity ETFs (XEQT, VEQT) or growth stocks in your TFSA.",
            })
        recommendations.append({
            "category": "Canadian Dividend Tax Credit",
            "tip": "In taxable non-registered accounts, hold Canadian dividend payers (VDY, XIU) to take advantage of the Federal Dividend Tax Credit.",
        })
    elif reg in ("INTL", "HK_TW", "TW", "HK", "SG"):
        recommendations.append({
            "category": "Ireland UCITS Alternative (Halve WHT from 30% to 15%)",
            "tip": "US-domiciled ETFs (VOO, SPY) suffer a punitive 30% dividend withholding tax for non-treaty investors. Switch to London-listed Ireland UCITS ETFs (e.g. CSPX, VUAA, SWRD) to cut dividend withholding to 15% and avoid 40% US Estate Tax.",
        })

    if weighted_ter > 0.30:
        recommendations.append({
            "category": "MER Compression",
            "tip": f"Your portfolio weighted expense ratio is {weighted_ter:.2f}%. Switching to core index ETFs (0.03%–0.08%, e.g. VOO/VTI/XIC) can preserve substantial retirement capital over 30 years.",
        })

    # 30-year summary stats
    h30 = history_10_20_30.get(30, {})
    total_loss_30 = h30.get("total_lost", h30.get("total_drag", 0.0))
    loss_ratio_30 = h30.get("pct_lost", h30.get("drag_pct", 0.0))
    gross_30 = h30.get("gross_wealth", 0.0)
    bench_30 = h30.get("benchmark_wealth", 0.0)
    port_30 = h30.get("portfolio_wealth", 0.0)

    fee_lost_base = h30.get("fee_lost", 0.0)
    tax_lost_base = h30.get("tax_lost", 0.0)

    total_tax_drag = annual_div_drag_pct + annual_cgt_drag_pct
    wht_s = (annual_div_drag_pct / total_tax_drag) if total_tax_drag > 0 else 0.0
    cgt_s = (annual_cgt_drag_pct / total_tax_drag) if total_tax_drag > 0 else 0.0

    thirty_fee_loss = fee_lost_base
    thirty_wht_loss = round(tax_lost_base * wht_s, 2)
    thirty_cgt_loss = round(tax_lost_base * cgt_s, 2)

    tips = [rec.get("tip", "") for rec in recommendations if "tip" in rec]

    return {
        "portfolio_initial": effective_port_val,
        "investor_region": reg,
        "region": reg,
        "account_type": acct,
        "portfolio_weighted_ter_pct": round(weighted_ter, 3),
        "weighted_ter_pct": round(weighted_ter, 3),
        "us_dividend_wht_pct": round(weighted_wht, 1),
        "weighted_wht_pct": round(weighted_wht, 1),
        "capital_gains_tax_pct": round(effective_cgt_pct, 1),
        "effective_cgt_pct": round(effective_cgt_pct, 1),
        "thirty_year_total_loss": total_loss_30,
        "thirty_year_loss_ratio_pct": loss_ratio_30,
        "thirty_year_fee_loss": thirty_fee_loss,
        "thirty_year_wht_loss": thirty_wht_loss,
        "thirty_year_cgt_loss": thirty_cgt_loss,
        "thirty_year_gross_wealth": gross_30,
        "thirty_year_benchmark_wealth": bench_30,
        "thirty_year_portfolio_wealth": port_30,
        "annual_div_drag_pct": annual_div_drag_pct,
        "annual_cgt_drag_pct": annual_cgt_drag_pct,
        "total_annual_friction_pct": total_annual_friction_pct,
        "benchmark_friction_pct": benchmark_total_friction_pct,
        "history_10_20_30": history_10_20_30,
        "trajectory": trajectory,
        "trajectories": trajectory,
        "holding_details": holding_details,
        "recommendations": recommendations,
        "asset_location_tips": tips,
        "bernstein_thesis": (
            "William J. Bernstein Pillar 4 Principle: In financial markets, you get what you don't pay for. "
            "A seemingly small 1.5% drag from fund fees, dividend withholding taxes, and capital gains leakage "
            "compounds exponentially over 30 years, quietly confiscating 30% to 45% of your lifetime retirement wealth."
        ),
    }


def calc_rebalancing_5_25_bands(
    holdings: Optional[List[Dict[str, Any]]] = None,
    target_weights: Optional[Dict[str, float]] = None,
    total_portfolio_val: float = 0.0,
    **kwargs,
) -> Dict[str, Any]:
    """
    Evaluates portfolio drift according to William J. Bernstein's 5/25 Rebalancing Rule
    ('The Four Pillars of Investing', Ch 14: 'The Rebalancing Bonus'):
    - An asset class triggers rebalancing when it deviates by:
      1. Greater than 5.0% absolute portfolio weight (e.g. target 40%, actual <35% or >45%), OR
      2. Greater than 25.0% relative to its target weight (e.g. target 10%, drift > 2.5%, actual <7.5% or >12.5%).
    - Minimizes unnecessary transaction fees while systematically capturing the contrarian 'Rebalancing Bonus' (+0.3% - +0.8%/yr).
    """
    if holdings is None:
        holdings = []

    if total_portfolio_val <= 0.0 and "portfolio_val" in kwargs:
        total_portfolio_val = float(kwargs["portfolio_val"])

    # Calculate actual weights
    holding_vals = {}
    tot_val = 0.0
    for h in holdings:
        sh = float(h.get("shares", 0.0) or 0.0)
        p = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
        sym = str(h.get("symbol", "")).strip().upper()
        clean_sym = sym.split(":")[0].split(".")[0].strip()
        v = sh * p
        tot_val += v
        holding_vals[clean_sym] = holding_vals.get(clean_sym, 0.0) + v

    eff_val = max(total_portfolio_val, tot_val)
    if eff_val <= 0:
        eff_val = 1.0

    actual_weights = {s: (v / eff_val * 100.0) for s, v in holding_vals.items()}

    # If target_weights not provided, infer equal target or classic Bernstein 40/60
    if not target_weights:
        if len(actual_weights) > 0:
            eq = round(100.0 / len(actual_weights), 1)
            target_weights = {s: eq for s in actual_weights}
        else:
            target_weights = {"VOO": 60.0, "TIP": 40.0}

    # Evaluate all symbols present in either actual or target
    all_syms = sorted(list(set(actual_weights.keys()).union(set(target_weights.keys()))))
    items = []
    triggered_count = 0
    approaching_count = 0

    for sym in all_syms:
        act = actual_weights.get(sym, 0.0)
        tgt = target_weights.get(sym, 0.0)

        abs_drift = round(act - tgt, 2)
        rel_drift = round((abs(abs_drift) / tgt * 100.0), 1) if tgt > 0 else 99.9

        # 5/25 Rule
        is_triggered = abs(abs_drift) >= 5.0 or rel_drift >= 25.0
        is_approaching = (not is_triggered) and (abs(abs_drift) >= 3.5 or rel_drift >= 17.5)

        if is_triggered:
            status = "triggered"
            triggered_count += 1
            action = "trim" if abs_drift > 0 else "add"
        elif is_approaching:
            status = "approaching"
            approaching_count += 1
            action = "hold"
        else:
            status = "in_band"
            action = "hold"

        delta_dollars = round((tgt - act) / 100.0 * eff_val, 2)

        items.append({
            "symbol": sym,
            "actual_pct": round(act, 1),
            "target_pct": round(tgt, 1),
            "abs_drift_pct": abs_drift,
            "rel_drift_pct": rel_drift,
            "status": status,
            "action": action,
            "delta_dollars": delta_dollars,
            "rebalance_amount_dollars": abs(delta_dollars),
        })

    # Sort so triggered appears first
    items.sort(key=lambda x: (0 if x["status"] == "triggered" else (1 if x["status"] == "approaching" else 2), -abs(x["abs_drift_pct"])))

    # Rebalancing bonus estimation (+0.50%/year on average)
    est_annual_bonus_pct = 0.50
    est_annual_bonus_dollars = round(eff_val * (est_annual_bonus_pct / 100.0), 2)

    thesis = (
        "William J. Bernstein: 'Calendar-based rebalancing (e.g. monthly) triggers needless taxable events and trading costs. "
        "Adopt the 5/25 rule: rebalance only when an asset moves 5% in absolute terms or 25% in relative terms. "
        "This contrarian discipline reaps an extra 0.3% to 0.8% annual return over time.'"
    )

    return {
        "portfolio_val": eff_val,
        "items": items,
        "asset_drifts": items,
        "bands": items,
        "total_assets": len(all_syms),
        "triggered_count": triggered_count,
        "approaching_count": approaching_count,
        "is_rebalance_needed": triggered_count > 0,
        "rebalancing_bonus_pct": est_annual_bonus_pct,
        "est_annual_bonus_pct": est_annual_bonus_pct,
        "estimated_annual_rebalance_bonus": est_annual_bonus_dollars,
        "est_annual_bonus_dollars": est_annual_bonus_dollars,
        "bernstein_rebalance_thesis": thesis,
        "bernstein_quote": thesis,
    }


def calc_simplicity_index(
    holdings: Optional[List[Dict[str, Any]]] = None,
    current_age: int = 60,
    total_portfolio_val: float = 0.0,
) -> Dict[str, Any]:
    """
    Evaluates portfolio operational simplicity and cognitive decline defense
    ('The Four Pillars of Investing', Pillar 3 & 'The Ages of the Investor'):
    - Protects retirees past age 75 from cognitive fatigue, emotional mistakes, and fraudulent exploitation.
    - Evaluates:
      1. Holding Count Penalty (1-4 ideal, >15 penalized).
      2. Broad Indexing Ratio (Passive index ETFs vs high-maintenance individual stock picking).
      3. Currency Simplicity (1-2 currencies vs fragmented multi-currency clutter).
    """
    if holdings is None:
        holdings = []

    age = max(18, min(100, int(current_age)))
    tot_val = 0.0
    index_val = 0.0
    currencies = set()

    for h in holdings:
        sh = float(h.get("shares", 0.0) or 0.0)
        p = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
        val = max(0.0, sh * p)
        tot_val += val

        c = str(h.get("currency", "USD")).upper()
        currencies.add(c)

        sym = str(h.get("symbol", "")).upper()
        clean = sym.split(":")[0].split(".")[0].strip()
        name = str(h.get("name", "")).upper()

        if clean in KNOWN_ETF_TER or "ETF" in name or "INDEX" in name or "FUND" in name:
            index_val += val

    eff_val = max(total_portfolio_val, tot_val)
    count = len(holdings)

    # 1. Holding count score (max 30)
    if count <= 4:
        count_score = 30.0
    elif count <= 8:
        count_score = 22.0
    elif count <= 15:
        count_score = 12.0
    else:
        count_score = 5.0

    # 2. Broad Indexing ratio (max 40)
    indexing_ratio = (index_val / eff_val) if eff_val > 0 else 1.0
    if indexing_ratio >= 0.85:
        index_score = 40.0
    elif indexing_ratio >= 0.50:
        index_score = 25.0
    elif indexing_ratio >= 0.20:
        index_score = 12.0
    else:
        index_score = 5.0

    # 3. Currency simplicity (max 20)
    curr_count = len(currencies) if currencies else 1
    if curr_count == 1:
        curr_score = 20.0
    elif curr_count == 2:
        curr_score = 15.0
    else:
        curr_score = 8.0

    # 4. Safe base simplicity (max 10)
    safe_score = 10.0

    total_score = round(count_score + index_score + curr_score + safe_score, 1)

    if total_score >= 85.0:
        grade = "A"
        grade_desc = "Sleep-Well-at-Night Fortress (極簡省心堡壘)"
    elif total_score >= 70.0:
        grade = "B"
        grade_desc = "Managed Efficiency (穩健可控)"
    elif total_score >= 50.0:
        grade = "C"
        grade_desc = "Moderate Complexity Overhead (維護負擔偏高)"
    else:
        grade = "D"
        grade_desc = "Cognitive Hazard & Complexity Risk (操作失誤與高維護負擔)"

    cognitive_alert = False
    cognitive_warning = ""
    if age >= 70 and total_score < 70.0:
        cognitive_alert = True
        cognitive_warning = (
            f"Retiree age ({age}, 70+) Alert: Financial cognitive decision-making capacity declines naturally with age. "
            f"Managing {count} positions with active stock picking creates high vulnerability to execution errors and fraud. "
            f"Bernstein strongly urges consolidating into a 2-Fund or 3-Fund indexed core."
        )

    recs = [
        f"Consolidate {count} individual positions into 2 or 3 ultra-low cost core index ETFs (e.g. VOO/VXUS/BND).",
        "Maintain adequate TIPS or short-term treasury reserve to immunize living expenses against market crashes.",
    ]
    if cognitive_warning:
        recs.insert(0, cognitive_warning)

    return {
        "simplicity_score": total_score,
        "simplicity_grade": grade,
        "rating": grade,
        "grade_desc": grade_desc,
        "rating_desc": grade_desc,
        "holding_count": count,
        "holding_score": count_score,
        "indexing_ratio_pct": round(indexing_ratio * 100.0, 1),
        "index_score": index_score,
        "currency_count": curr_count,
        "currency_score": curr_score,
        "cognitive_alert": cognitive_alert,
        "cognitive_warning": cognitive_warning,
        "recommendations": recs,
        "recommended_consolidation": "40% TIPS/Short Treasuries (TIP/VGSH) + 60% Global All-Cap Equity (VOO/VXUS or XEQT)",
        "bernstein_thesis": (
            "William J. Bernstein Cognitive Decline Thesis: In our 40s and 50s, we believe we will always be sharp investors. "
            "By our late 70s and 80s, cognitive decline touches everyone. A 30-stock portfolio is an accident waiting to happen. "
            "True financial mastery is simplifying down to 2 or 3 total-market funds before you need to."
        ),
    }


def calc_fire_metrics(
    current_annual_div: float,
    target_monthly_expense: float,
    expected_div_growth: float = 0.05,
    current_portfolio_val: float = 0.0,
    monthly_savings: float = 0.0,
    guaranteed_annual_pension: float = 0.0,
    target_safe_years: float = 25.0,
    current_age: int = 45,
    retire_age: int = 60,
    life_expectancy: int = 90,
    current_safe_assets: float = 0.0,
    delay_pension_to_70: bool = False,
    essential_monthly_expense: float = 0.0,
    discretionary_monthly_expense: float = 0.0,
    current_cape: float = 34.0,
    holdings: Optional[List[Dict[str, Any]]] = None,
    investor_region: str = "CA",
    account_type: str = "taxable",
    custom_cgt_rate: Optional[float] = None,
    target_weights: Optional[Dict[str, float]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Computes Financial Independence / Retire Early (FIRE) metrics based on
    William J. Bernstein's core frameworks ('The Four Pillars of Investing'):
    1. Step 1: Existing Holdings & Safe Asset Audit (Equities vs. Safe Debt Assets).
    2. Step 2: Age, Target Retirement Timeline & Strategy (Years to retire, horizon).
    3. Step 3: Residual Living Expenses (RLE) = Total Expenses - Guaranteed Pension.
       Two-Tier Expense Model: Essential Floor vs. Discretionary Spending.
    4. Step 4: Gap Analysis — What Is Missing? (Safe liability gap, dividend gap, capital gap).
    5. Step 5: Burn Rate (%) & Actionable Master Plan (<2% Abundant, 2-3.5% Safe, >3.5% Sequence Risk).
    """
    investor_region = kwargs.get("tax_region", kwargs.get("region", investor_region))
    account_type = kwargs.get("account_type", account_type)

    ann_div = max(0.0, float(current_annual_div))
    mo_exp = max(0.0, float(target_monthly_expense))
    
    # Two-tier expense modeling: Essential Floor vs Discretionary Ceiling
    ess_exp_mo = max(0.0, float(essential_monthly_expense))
    disc_exp_mo = max(0.0, float(discretionary_monthly_expense))

    if ess_exp_mo <= 0.0 and disc_exp_mo <= 0.0:
        # Default: 70% essential floor, 30% discretionary lifestyle
        ess_exp_mo = round(mo_exp * 0.70, 2)
        disc_exp_mo = round(max(0.0, mo_exp - ess_exp_mo), 2)
    elif ess_exp_mo > 0.0 and disc_exp_mo <= 0.0:
        disc_exp_mo = round(max(0.0, mo_exp - ess_exp_mo), 2)
    elif disc_exp_mo > 0.0 and ess_exp_mo <= 0.0:
        ess_exp_mo = round(max(0.0, mo_exp - disc_exp_mo), 2)
    else:
        # Both provided: sync mo_exp
        mo_exp = round(ess_exp_mo + disc_exp_mo, 2)

    ann_exp = round(mo_exp * 12.0, 2)
    ess_ann_exp = round(ess_exp_mo * 12.0, 2)
    disc_ann_exp = round(disc_exp_mo * 12.0, 2)

    pension_ann_base = max(0.0, float(guaranteed_annual_pension))
    
    # Delay to 70 strategy: Bernstein Ch 16-17 notes delaying past 65 yields ~8%/yr permanent boost (~28% boost)
    pension_ann = round(pension_ann_base * 1.28, 2) if (delay_pension_to_70 and pension_ann_base > 0) else pension_ann_base
    pension_mo = round(pension_ann / 12.0, 2)
    
    div_growth = max(0.0, min(0.30, float(expected_div_growth)))
    port_val = max(0.0, float(current_portfolio_val))
    mo_savings = max(0.0, float(monthly_savings))
    safe_years = max(10.0, min(40.0, float(target_safe_years)))
    cur_age = max(18, min(100, int(current_age)))
    ret_age = max(cur_age, min(105, int(retire_age)))
    life_exp = max(ret_age + 1, min(120, int(life_expectancy)))
    cur_safe = max(0.0, float(current_safe_assets))

    years_to_retire = max(0, ret_age - cur_age)
    retirement_duration_years = max(5, life_exp - ret_age)

    # 1. Residual Living Expenses (RLE) - 待攤生活費用
    rle_annual = round(max(0.0, ann_exp - pension_ann), 2)
    rle_monthly = round(rle_annual / 12.0, 2)

    # Essential Floor RLE (Essential spending after guaranteed pension)
    essential_rle_annual = round(max(0.0, ess_ann_exp - pension_ann), 2)
    essential_rle_monthly = round(essential_rle_annual / 12.0, 2)

    # Essential Floor Coverage: Does Pension + Safe Asset Annuity 100% cover essential floor?
    safe_annual_draw = (cur_safe / safe_years) if safe_years > 0 else 0.0
    essential_guaranteed_inflow = pension_ann + safe_annual_draw
    essential_floor_coverage_pct = round(min(500.0, (essential_guaranteed_inflow / ess_ann_exp * 100.0)), 1) if ess_ann_exp > 0 else 100.0
    essential_floor_is_safe = essential_guaranteed_inflow >= ess_ann_exp

    # Discretionary Coverage: How well do dividends cover discretionary lifestyle spending?
    discretionary_buffer_pct = round(min(500.0, (ann_div / disc_ann_exp * 100.0)), 1) if disc_ann_exp > 0 else 100.0

    # 2. Burn Rate (%) - 燒錢率
    burn_rate_pct = round((rle_annual / port_val * 100.0), 2) if port_val > 0 else (0.0 if rle_annual == 0 else 99.9)
    if burn_rate_pct <= 2.0 or rle_annual == 0:
        burn_zone = "green"
        burn_zone_desc = "Safe & Abundant (< 2.0%) - Frank Zone"
        bernstein_tip = (
            "Bernstein Wisdom: You have won the game! With a burn rate under 2%, your retirement is exceptionally secure. "
            "Your safe liabilities are easily covered, and your surplus can fund legacy, charity, or conservative equity growth."
        )
    elif burn_rate_pct <= 3.5:
        burn_zone = "yellow"
        burn_zone_desc = "Sustainable Zone (2.0% - 3.5%) - Bernstein Target"
        bernstein_tip = (
            "Bernstein Wisdom: Your burn rate is in the sustainable corridor (2.0% - 3.5%). "
            "Delay pensions/Social Security to age 70 for inflation-protected longevity insurance, and maintain a 20-25 year liability buffer."
        )
    else:
        burn_zone = "red"
        burn_zone_desc = "High Sequence Risk Zone (> 3.5%) - Fritz Vulnerable"
        bernstein_tip = (
            "Bernstein Warning: High sequence-of-returns risk (> 3.5% burn rate)! "
            "A bear market in early retirement could cause permanent capital impairment. Prioritize building 20-25 years of safe assets."
        )

    # 3. Liability Matching Portfolio vs. Risk Portfolio
    liability_matching_20y = round(rle_annual * 20.0, 2)
    liability_matching_25y = round(rle_annual * 25.0, 2)
    liability_matching_target = round(rle_annual * safe_years, 2)
    liability_coverage_pct = round(min(500.0, (port_val / liability_matching_target * 100.0)), 2) if liability_matching_target > 0 else 100.0
    risk_portfolio_surplus = round(port_val - liability_matching_target, 2)

    # Safe Asset Gap Analysis: What is missing in fixed income / TIPS?
    safe_asset_gap = round(max(0.0, liability_matching_target - cur_safe), 2)
    safe_asset_surplus = round(max(0.0, cur_safe - liability_matching_target), 2)
    safe_asset_coverage_pct = round(min(500.0, (cur_safe / liability_matching_target * 100.0)), 2) if liability_matching_target > 0 else 100.0

    # 4. Dual-Engine Targets: Capital Target (3.2% vs 4%) & Dividend Runway
    fire_number_4pct = round(rle_annual * 25.0, 2) if rle_annual > 0 else 0.0
    bernstein_swr_32_target = round(rle_annual * 31.25, 2) if rle_annual > 0 else 0.0

    curr_div_yield = (ann_div / port_val) if port_val > 0 else 0.04
    fire_number_yield = round(rle_annual / curr_div_yield, 2) if (curr_div_yield > 0 and rle_annual > 0) else fire_number_4pct

    # Dividend Runway Coverage on RLE
    freedom_pct = round(min(100.0, (ann_div / rle_annual * 100.0)), 2) if rle_annual > 0 else 100.0
    dividend_rle_coverage_pct = round(min(500.0, (ann_div / rle_annual * 100.0)), 2) if rle_annual > 0 else 100.0
    monthly_div = round(ann_div / 12.0, 2)
    monthly_shortfall = round(max(0.0, rle_monthly - monthly_div), 2)

    # Dividend Gap & Capital Gap
    dividend_gap_annual = round(max(0.0, rle_annual - ann_div), 2)
    dividend_gap_monthly = round(dividend_gap_annual / 12.0, 2)
    capital_gap_bernstein = round(max(0.0, bernstein_swr_32_target - port_val), 2)
    capital_gap_4pct = round(max(0.0, fire_number_4pct - port_val), 2)

    # Monthly savings needed to bridge capital gap by retirement age
    if years_to_retire > 0 and capital_gap_bernstein > 0:
        monthly_savings_needed = round(capital_gap_bernstein / (years_to_retire * 12.0), 2)
    else:
        monthly_savings_needed = 0.0

    # 5. Project years to 100% crossover of RLE
    proj_years = 0
    sim_div = ann_div
    sim_port = port_val
    max_sim = 40

    while proj_years < max_sim and sim_div < rle_annual:
        proj_years += 1
        growth_amt = sim_div * div_growth
        new_capital = sim_div + (mo_savings * 12.0)
        new_div = new_capital * curr_div_yield
        sim_div += growth_amt + new_div
        sim_port += new_capital

    milestones_list = [
        {"name": "25% (Coast FIRE)", "target": round(rle_annual * 0.25, 2), "pct": 25.0, "reached": ann_div >= (rle_annual * 0.25)},
        {"name": "50% (Barista FIRE)", "target": round(rle_annual * 0.50, 2), "pct": 50.0, "reached": ann_div >= (rle_annual * 0.50)},
        {"name": "75% (Lean FIRE)", "target": round(rle_annual * 0.75, 2), "pct": 75.0, "reached": ann_div >= (rle_annual * 0.75)},
        {"name": "100% (Full Financial Independence)", "target": round(rle_annual, 2), "pct": 100.0, "reached": ann_div >= rle_annual},
        {"name": "150% (Abundant / Legacy FIRE)", "target": round(rle_annual * 1.50, 2), "pct": 150.0, "reached": ann_div >= (rle_annual * 1.50)},
    ]
    milestones_dict = {
        "coast": round(rle_annual * 0.25, 2),
        "barista": round(rle_annual * 0.50, 2),
        "lean": round(rle_annual * 0.75, 2),
        "full": round(rle_annual, 2),
        "abundant": round(rle_annual * 1.50, 2),
    }

    # Concrete Bernstein recommendations for bridging gaps
    recommended_safe_instruments = [
        {"symbol": "TIP", "name": "iShares TIPS Bond ETF", "type": "TIPS (美國通膨保值公債)", "desc": "100% 政府信用，本金隨 CPI 通膨指數上調"},
        {"symbol": "VTIP", "name": "Vanguard Short-Term TIPS", "type": "短期 TIPS (0-5年)", "desc": "超低利率久期風險，完美抵禦生活物價通膨"},
        {"symbol": "VGSH", "name": "Vanguard Short-Term Treasury", "type": "短期國債 (1-3年)", "desc": "最高流動性，市場崩盤時的堅實防禦底層"},
        {"symbol": "XSB.TO", "name": "iShares Canadian Short Bond", "type": "加幣短期公債/優質債", "desc": "加拿大居民專屬低波動防禦資產"},
        {"symbol": "CASH.TO", "name": "Global X High Interest Savings", "type": "高利銀行存款 ETF", "desc": "完全無本金虧損風險，提供穩定月度現金利息"},
    ]

    recommended_equity_instruments = [
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "type": "美股大盤核心", "desc": "涵蓋美國 500 大跨國龍頭，長期年化 9%-10%"},
        {"symbol": "SCHD", "name": "Schwab US Dividend Equity", "type": "高股息成長龍頭", "desc": "10 年以上股息連續成長績優企業，殖利率 ~3.5%"},
        {"symbol": "VDY.TO", "name": "Vanguard Canadian High Dividend", "type": "加拿大高股息", "desc": "聚焦加拿大優質銀行與公用事業，月度現金流"},
        {"symbol": "0005.HK", "name": "HSBC Holdings (匯豐控股)", "type": "港股核心金融藍籌", "desc": "長期穩定分紅，亞洲退休族經典被動現金流"},
    ]

    # Precompute 20-25 year TIPS / Safe Bond Ladder and Pension Actuary
    ladder_data = calc_bond_ladder_schedule(
        rle_annual=rle_annual,
        safe_years=safe_years,
        start_age=ret_age,
        current_safe_assets=cur_safe,
        annual_inflation=0.025,
    )
    pension_actuary_data = calc_pension_actuarial_comparison(
        base_annual_pension_at_65=pension_ann_base,
        current_age=cur_age,
        life_expectancy=life_exp,
    )

    # Precompute Bernstein Phase 2 Risk Defense Models
    deep_risk_data = calc_deep_risk_diagnostic(
        holdings=holdings,
        safe_assets_val=cur_safe,
        total_portfolio_val=port_val,
    )
    crisis_stress_test_data = calc_historical_crisis_stress_test(
        portfolio_val=port_val,
        rle_annual=rle_annual,
        safe_assets_val=cur_safe,
        safe_years=safe_years,
    )
    cape_swr_data = calc_cape_dynamic_swr(
        current_cape=current_cape,
        base_swr=0.032,
        portfolio_val=port_val,
    )

    # Precompute Bernstein Phase 3 Optimization & Friction Models
    fee_tax_data = calc_fee_and_tax_drag_autopsy(
        holdings=holdings,
        portfolio_val=port_val,
        investor_region=investor_region,
        account_type=account_type,
        custom_cgt_rate_pct=custom_cgt_rate,
    )
    rebalance_5_25_data = calc_rebalancing_5_25_bands(
        holdings=holdings,
        target_weights=target_weights,
        total_portfolio_val=port_val,
    )
    simplicity_data = calc_simplicity_index(
        holdings=holdings,
        current_age=cur_age,
        total_portfolio_val=port_val,
    )

    # 10 Advanced Retirement Models
    spending_smile_data = calc_retirement_spending_smile(
        base_annual_spending=ann_exp,
        retire_age=ret_age,
        life_expectancy=life_exp,
    )
    srr_data = calc_sequence_of_returns_risk_simulation(
        portfolio_val=port_val,
        annual_withdrawal=rle_annual,
        safe_assets_val=cur_safe,
    )
    guardrails_data = calc_guyton_klinger_guardrails(
        portfolio_val=port_val,
        current_annual_withdrawal=rle_annual,
    )
    three_bucket_data = calc_three_bucket_architecture(
        total_wealth=port_val + cur_safe,
        annual_rle=rle_annual,
        current_safe_assets=cur_safe,
    )
    ltc_data = calc_healthcare_ltc_contingency(
        portfolio_val=port_val + cur_safe,
        current_age=cur_age,
    )
    longevity_data = calc_actuarial_longevity_table(
        current_age=cur_age,
    )
    monte_carlo_dist = calc_monte_carlo_distribution(
        portfolio_val=port_val + cur_safe,
        annual_withdrawal=rle_annual,
        years=retirement_duration_years,
    )
    stagflation_data = calc_stagflation_sensitivity_matrix(
        portfolio_val=port_val + cur_safe,
        annual_withdrawal=rle_annual,
    )
    glidepath_data = calc_rising_equity_glidepath(
        current_age=cur_age,
        retire_age=ret_age,
        current_equity_pct=round((port_val / (port_val + cur_safe) * 100.0), 1) if (port_val + cur_safe) > 0 else 60.0,
    )

    return {
        "current_age": cur_age,
        "retire_age": ret_age,
        "life_expectancy": life_exp,
        "years_to_retire": years_to_retire,
        "retirement_duration_years": retirement_duration_years,
        "delay_pension_to_70": delay_pension_to_70,
        "current_portfolio_val": port_val,
        "total_effective_wealth": port_val,
        "monthly_savings": mo_savings,
        "expected_div_growth": div_growth,
        "current_cape": current_cape,
        "target_monthly_expense": round(mo_exp, 2),
        "target_annual_expense": round(ann_exp, 2),
        "essential_monthly_expense": round(ess_exp_mo, 2),
        "essential_annual_expense": round(ess_ann_exp, 2),
        "discretionary_monthly_expense": round(disc_exp_mo, 2),
        "discretionary_annual_expense": round(disc_ann_exp, 2),
        "essential_rle_annual": essential_rle_annual,
        "essential_rle_monthly": essential_rle_monthly,
        "essential_floor_coverage_pct": essential_floor_coverage_pct,
        "essential_floor_is_safe": essential_floor_is_safe,
        "discretionary_buffer_pct": discretionary_buffer_pct,
        "guaranteed_annual_pension": round(pension_ann, 2),
        "guaranteed_annual_pension_base": round(pension_ann_base, 2),
        "guaranteed_monthly_pension": pension_mo,
        "rle_annual": rle_annual,
        "rle_monthly": rle_monthly,
        "current_safe_assets": cur_safe,
        "current_annual_dividend": round(ann_div, 2),
        "current_monthly_dividend": monthly_div,
        "monthly_shortfall": monthly_shortfall,
        "burn_rate_pct": burn_rate_pct,
        "burn_zone": burn_zone,
        "burn_zone_desc": burn_zone_desc,
        "target_safe_years": safe_years,
        "liability_matching_target": liability_matching_target,
        "liability_matching_20y": liability_matching_20y,
        "liability_matching_25y": liability_matching_25y,
        "liability_coverage_pct": liability_coverage_pct,
        "safe_asset_gap": safe_asset_gap,
        "safe_asset_surplus": safe_asset_surplus,
        "safe_asset_coverage_pct": safe_asset_coverage_pct,
        "dividend_gap_annual": dividend_gap_annual,
        "dividend_gap_monthly": dividend_gap_monthly,
        "capital_gap_bernstein": capital_gap_bernstein,
        "capital_gap_4pct": capital_gap_4pct,
        "monthly_savings_needed": monthly_savings_needed,
        "risk_portfolio_surplus": risk_portfolio_surplus,
        "freedom_percentage": freedom_pct,
        "freedom_coverage_pct": freedom_pct,
        "dividend_rle_coverage_pct": dividend_rle_coverage_pct,
        "fire_target_capital_4pct": fire_number_4pct,
        "fire_number_4pct": fire_number_4pct,
        "bernstein_swr_32_target": bernstein_swr_32_target,
        "fire_target_capital_yield": fire_number_yield,
        "projected_years_to_freedom": proj_years if proj_years < max_sim else "30+",
        "years_to_crossover": float(proj_years) if proj_years < max_sim else 99.0,
        "milestones": milestones_dict,
        "milestones_list": milestones_list,
        "recommended_safe_instruments": recommended_safe_instruments,
        "recommended_equity_instruments": recommended_equity_instruments,
        "bernstein_tip": bernstein_tip,
        "ladder_data": ladder_data,
        "pension_actuary_data": pension_actuary_data,
        "deep_risk_data": deep_risk_data,
        "crisis_stress_test_data": crisis_stress_test_data,
        "cape_swr_data": cape_swr_data,
        "fee_tax_data": fee_tax_data,
        "rebalance_5_25_data": rebalance_5_25_data,
        "simplicity_data": simplicity_data,
        "spending_smile_data": spending_smile_data,
        "srr_data": srr_data,
        "guardrails_data": guardrails_data,
        "three_bucket_data": three_bucket_data,
        "ltc_data": ltc_data,
        "longevity_data": longevity_data,
        "monte_carlo_dist": monte_carlo_dist,
        "stagflation_data": stagflation_data,
        "glidepath_data": glidepath_data,
    }


# -------------------------------------------------------------------------
# Core Suggested Asset Allocation ETFs & Portfolio Presets
# -------------------------------------------------------------------------

SUGGESTED_ALLOCATION_ETFS: List[Dict[str, Any]] = [
    # US Equity Core & Growth
    {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "asset_class": "US Large-Cap Equity", "asset_class_zh_tw": "美股大型股", "asset_class_zh_cn": "美股大型股", "currency": "USD", "typical_price": 500.0, "desc": "Top 500 US companies, rock-bottom 0.03% expense ratio"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "asset_class": "US Total Market", "asset_class_zh_tw": "美股全市場", "asset_class_zh_cn": "美股全市场", "currency": "USD", "typical_price": 270.0, "desc": "Entire US investable universe (~3,600 stocks)"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust (Nasdaq 100)", "asset_class": "US Tech & Growth", "asset_class_zh_tw": "美股科技與成長", "asset_class_zh_cn": "美股科技与成长", "currency": "USD", "typical_price": 490.0, "desc": "Top 100 non-financial Nasdaq innovators"},
    {"symbol": "SCHD", "name": "Schwab U.S. Dividend Equity ETF", "asset_class": "US Dividend Growth", "asset_class_zh_tw": "美股股息成長", "asset_class_zh_cn": "美股股息成长", "currency": "USD", "typical_price": 82.0, "desc": "High-quality cash cows with consecutive dividend hikes"},

    # Global & International Equity
    {"symbol": "VXUS", "name": "Vanguard Total International Stock ETF", "asset_class": "Global ex-US All-Cap", "asset_class_zh_tw": "全球非美全市場", "asset_class_zh_cn": "全球非美全市场", "currency": "USD", "typical_price": 62.0, "desc": "Covers Europe, Pacific, and Emerging Markets (~8,500 stocks)"},
    {"symbol": "VEA", "name": "Vanguard FTSE Developed Markets ETF", "asset_class": "Developed International", "asset_class_zh_tw": "國際已開發市場", "asset_class_zh_cn": "国际已开发市场", "currency": "USD", "typical_price": 52.0, "desc": "Europe, Japan, UK, Australia developed economies"},
    {"symbol": "VWO", "name": "Vanguard FTSE Emerging Markets ETF", "asset_class": "Emerging Markets", "asset_class_zh_tw": "新興市場", "asset_class_zh_cn": "新兴市场", "currency": "USD", "typical_price": 45.0, "desc": "High-growth economies: Taiwan, India, China, Brazil"},
    {"symbol": "VT", "name": "Vanguard Total World Stock ETF", "asset_class": "All-World Global Equity", "asset_class_zh_tw": "全球全市場股票", "asset_class_zh_cn": "全球全市场股票", "currency": "USD", "typical_price": 115.0, "desc": "Ultimate single-ticket world stock market (~9,800 stocks)"},

    # Canadian Core & All-in-One Asset Allocation
    {"symbol": "VFV:TSE", "name": "Vanguard S&P 500 Index ETF (CAD)", "asset_class": "US Equity (CAD)", "asset_class_zh_tw": "美股大盤(加幣)", "asset_class_zh_cn": "美股大盘(加元)", "currency": "CAD", "typical_price": 140.0, "desc": "S&P 500 traded directly in Canadian Dollars on TSX"},
    {"symbol": "XEQT:TSE", "name": "iShares Core Equity ETF Portfolio", "asset_class": "All-Equity Global", "asset_class_zh_tw": "全球全股票(加幣)", "asset_class_zh_cn": "全球全股票(加元)", "currency": "CAD", "typical_price": 32.0, "desc": "100% globally diversified equity portfolio in a single CAD ETF"},
    {"symbol": "VGRO:TSE", "name": "Vanguard Growth ETF Portfolio", "asset_class": "80/20 Growth Balanced", "asset_class_zh_tw": "80/20 成長平衡(加幣)", "asset_class_zh_cn": "80/20 成长平衡(加元)", "currency": "CAD", "typical_price": 37.0, "desc": "80% Global Equity + 20% Fixed Income all-in-one"},
    {"symbol": "XEF:TSE", "name": "iShares Core MSCI EAFE IMI Index ETF", "asset_class": "International Equity (CAD)", "asset_class_zh_tw": "國際成熟市場(加幣)", "asset_class_zh_cn": "国际成熟市场(加元)", "currency": "CAD", "typical_price": 40.0, "desc": "Direct European and Asian market coverage in CAD"},
    {"symbol": "VDY:TSE", "name": "Vanguard Canadian High Dividend Yield", "asset_class": "Canadian Dividend Cashflow", "asset_class_zh_tw": "加拿大高股息現金流", "asset_class_zh_cn": "加拿大高股息现金流", "currency": "CAD", "typical_price": 45.0, "desc": "Focus on high-yield Canadian banks, telcos, utilities"},
    {"symbol": "XIU:TSE", "name": "iShares S&P/TSX 60 Index ETF", "asset_class": "Canadian Large-Cap", "asset_class_zh_tw": "加拿大藍籌60", "asset_class_zh_cn": "加拿大蓝筹60", "currency": "CAD", "typical_price": 36.0, "desc": "60 largest, liquid benchmark Canadian corporations"},

    # Fixed Income / Safe Assets (Bernstein Liability Matching & Safe Haven)
    {"symbol": "BND", "name": "Vanguard Total Bond Market ETF", "asset_class": "US Total Bond Market", "asset_class_zh_tw": "美國全債券市場", "asset_class_zh_cn": "美国全债券市场", "currency": "USD", "typical_price": 73.0, "desc": "US Treasuries and investment-grade corporate bonds"},
    {"symbol": "ZAG:TSE", "name": "BMO Aggregate Bond Index ETF", "asset_class": "Canadian Aggregate Bonds", "asset_class_zh_tw": "加拿大綜合債券", "asset_class_zh_cn": "加拿大综合债券", "currency": "CAD", "typical_price": 13.5, "desc": "Federal, provincial, and corporate Canadian bonds"},
    {"symbol": "TIP", "name": "iShares TIPS Bond ETF", "asset_class": "US TIPS Inflation-Protected", "asset_class_zh_tw": "美國抗通膨公債(TIPS)", "asset_class_zh_cn": "美国抗通胀国债(TIPS)", "currency": "USD", "typical_price": 108.0, "desc": "Principal adjusts with US CPI inflation; deflation protection"},
    {"symbol": "XSB:TSE", "name": "iShares Canadian Short Term Bond", "asset_class": "Canadian Short-Term Bonds", "asset_class_zh_tw": "加拿大短期公債", "asset_class_zh_cn": "加拿大短期国债", "currency": "CAD", "typical_price": 27.0, "desc": "Low interest-rate duration risk, high capital stability"},
    {"symbol": "CASH:TSE", "name": "Global X High Interest Savings ETF", "asset_class": "High-Interest Cash Deposits", "asset_class_zh_tw": "高利現金存款ETF", "asset_class_zh_cn": "高利现金存款ETF", "currency": "CAD", "typical_price": 50.0, "desc": "Deposits in Tier-1 Canadian banks, monthly income"},

    # Alternatives / Real Assets / Commodities
    {"symbol": "GLD", "name": "SPDR Gold Shares", "asset_class": "Physical Gold Bullion", "asset_class_zh_tw": "實體黃金避險", "asset_class_zh_cn": "实物黄金避险", "currency": "USD", "typical_price": 240.0, "desc": "Classic crisis hedge and currency debasement safe haven"},
    {"symbol": "VNQ", "name": "Vanguard Real Estate ETF", "asset_class": "US Real Estate / REITs", "asset_class_zh_tw": "美國房地產REITs", "asset_class_zh_cn": "美国房地产REITs", "currency": "USD", "typical_price": 88.0, "desc": "Commercial, residential, healthcare properties cashflow"},
]

ALLOCATION_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "bogle_3fund",
        "name": "🏛️ Bogleheads 3-Fund (60% VTI + 20% VXUS + 20% BND)",
        "name_zh_tw": "🏛️ 柏格頭經典三基金 (60% VTI + 20% VXUS + 20% BND)",
        "name_zh_cn": "🏛️ 博格头经典三基金 (60% VTI + 20% VXUS + 20% BND)",
        "weights": {"VTI": 60.0, "VXUS": 20.0, "BND": 20.0},
        "desc": "Jack Bogle's classic low-cost total market indexing strategy.",
    },
    {
        "id": "couch_potato",
        "name": "🍁 Canadian Couch Potato (80% VGRO:TSE + 20% ZAG:TSE)",
        "name_zh_tw": "🍁 加拿大沙發馬鈴薯模型 (80% VGRO:TSE + 20% ZAG:TSE)",
        "name_zh_cn": "🍁 加拿大沙发土豆模型 (80% VGRO:TSE + 20% ZAG:TSE)",
        "weights": {"VGRO:TSE": 80.0, "ZAG:TSE": 20.0},
        "desc": "Canada's premier low-maintenance balanced growth model.",
    },
    {
        "id": "bernstein_fire",
        "name": "🔥 Bernstein Two-Track FIRE (40% TIP/BND + 60% VOO/VXUS)",
        "name_zh_tw": "🔥 伯恩斯坦雙軌退休模型 (40% TIP/BND + 60% VOO/VXUS)",
        "name_zh_cn": "🔥 伯恩斯坦双轨退休模型 (40% TIP/BND + 60% VOO/VXUS)",
        "weights": {"TIP": 20.0, "BND": 20.0, "VOO": 40.0, "VXUS": 20.0},
        "desc": "William J. Bernstein: 20-25 yrs liability matching bonds + global equity engine.",
    },
    {
        "id": "all_weather",
        "name": "🌦️ Ray Dalio All Weather (30% VOO + 40% BND + 15% TIP + 7.5% GLD + 7.5% VNQ)",
        "name_zh_tw": "🌦️ 達利歐全天候策略 (30% VOO + 40% BND + 15% TIP + 7.5% GLD + 7.5% VNQ)",
        "name_zh_cn": "🌦️ 达利欧全天候策略 (30% VOO + 40% BND + 15% TIP + 7.5% GLD + 7.5% VNQ)",
        "weights": {"VOO": 30.0, "BND": 40.0, "TIP": 15.0, "GLD": 7.5, "VNQ": 7.5},
        "desc": "Designed by Bridgewater to perform across all economic cycles.",
    },
    {
        "id": "dividend_income",
        "name": "💰 High Dividend Cashflow Engine (40% SCHD + 30% VDY:TSE + 30% ZAG:TSE)",
        "name_zh_tw": "💰 高股息現金流引擎 (40% SCHD + 30% VDY:TSE + 30% ZAG:TSE)",
        "name_zh_cn": "💰 高股息现金流引擎 (40% SCHD + 30% VDY:TSE + 30% ZAG:TSE)",
        "weights": {"SCHD": 40.0, "VDY:TSE": 30.0, "ZAG:TSE": 30.0},
        "desc": "Maximum passive monthly and quarterly dividend yield.",
    },
    {
        "id": "pure_global_equity",
        "name": "🚀 Global 100% Equity Growth (60% VOO + 20% QQQ + 20% VXUS)",
        "name_zh_tw": "🚀 全球100%股票積極成長 (60% VOO + 20% QQQ + 20% VXUS)",
        "name_zh_cn": "🚀 全球100%股票积极成长 (60% VOO + 20% QQQ + 20% VXUS)",
        "weights": {"VOO": 60.0, "QQQ": 20.0, "VXUS": 20.0},
        "desc": "Aggressive accumulation phase for long-horizon investors.",
    },
]


def get_preset_display_name(preset: Dict[str, Any], lang: str = "en") -> str:
    """Returns localized display name for an allocation preset."""
    if lang == "zh_TW":
        return preset.get("name_zh_tw", preset.get("name", ""))
    elif lang == "zh_CN":
        return preset.get("name_zh_cn", preset.get("name", ""))
    return preset.get("name", "")


def get_etf_option_label(etf: Dict[str, Any], lang: str = "en") -> str:
    """Returns formatted option string for suggested ETF combobox with localized asset class."""
    sym = etf.get("symbol", "")
    name = etf.get("name", "")
    aclass = etf.get("asset_class", "")
    if lang == "zh_TW":
        aclass = etf.get("asset_class_zh_tw", aclass)
    elif lang == "zh_CN":
        aclass = etf.get("asset_class_zh_cn", aclass)
    return f"{sym} — {name} ({aclass})"


# =====================================================================
# 10 ADVANCED RETIREMENT & ACTUARIAL FINANCIAL MODELS
# =====================================================================

def calc_retirement_spending_smile(
    base_annual_spending: float,
    retire_age: int = 60,
    life_expectancy: int = 90,
    active_end_age: int = 72,
    slow_end_age: int = 82,
    active_adjustment_pct: float = 8.0,
    slow_adjustment_pct: float = -20.0,
    care_adjustment_pct: float = 8.0,
) -> Dict[str, Any]:
    """
    1. David Blanchett (Morningstar) Retirement Spending Smile Model.
    Retirees experience three distinct spending phases:
      - Phase 1: Go-Go (Active: travel, lifestyle, projects) -> higher spending (+8%)
      - Phase 2: Slow-Go (Passive: home-based, lower activity) -> lower spending (-20%)
      - Phase 3: No-Go (Care: assisted living, healthcare, support) -> higher spending (+8%)
    """
    ret_age = max(40, int(retire_age))
    life_exp = max(ret_age + 1, int(life_expectancy))
    act_end = max(ret_age, min(life_exp - 1, int(active_end_age)))
    slow_end = max(act_end + 1, min(life_exp, int(slow_end_age)))

    annual_schedule = []
    flat_total = 0.0
    smile_total = 0.0

    for age in range(ret_age, life_exp + 1):
        if age <= act_end:
            phase = "active_gogo"
            phase_desc = "Go-Go (Active Lifestyle)"
            mult = 1.0 + (active_adjustment_pct / 100.0)
        elif age <= slow_end:
            phase = "passive_slowgo"
            phase_desc = "Slow-Go (Moderate Routine)"
            mult = 1.0 + (slow_adjustment_pct / 100.0)
        else:
            phase = "care_nogo"
            phase_desc = "No-Go (Healthcare / Assisted Living)"
            mult = 1.0 + (care_adjustment_pct / 100.0)

        phase_spending = round(base_annual_spending * mult, 2)
        flat_spending = round(base_annual_spending, 2)
        flat_total += flat_spending
        smile_total += phase_spending

        annual_schedule.append({
            "age": age,
            "year": age - ret_age + 1,
            "phase": phase,
            "phase_desc": phase_desc,
            "multiplier": round(mult, 2),
            "spending": phase_spending,
            "annual_spending": phase_spending,
            "flat_spending": flat_spending,
            "cumulative_total": round(smile_total, 2),
            "diff": round(phase_spending - flat_spending, 2),
        })

    capital_savings = round(flat_total - smile_total, 2)
    savings_pct = round((capital_savings / flat_total * 100.0), 2) if flat_total > 0 else 0.0

    return {
        "retire_age": ret_age,
        "life_expectancy": life_exp,
        "active_end_age": act_end,
        "slow_end_age": slow_end,
        "base_annual_spending": round(base_annual_spending, 2),
        "gogo_annual": round(base_annual_spending * (1.0 + active_adjustment_pct / 100.0), 2),
        "slowgo_annual": round(base_annual_spending * (1.0 + slow_adjustment_pct / 100.0), 2),
        "care_annual": round(base_annual_spending * (1.0 + care_adjustment_pct / 100.0), 2),
        "flat_total_spending": round(flat_total, 2),
        "smile_total_spending": round(smile_total, 2),
        "flat_total_lifetime": round(flat_total, 2),
        "smile_total_lifetime": round(smile_total, 2),
        "capital_savings": capital_savings,
        "savings_pct": savings_pct,
        "annual_schedule": annual_schedule,
    }


def calc_sequence_of_returns_risk_simulation(
    portfolio_val: float,
    annual_withdrawal: float,
    safe_assets_val: float = 0.0,
    crash_scenario: str = "stagflation_1973",
    real_return_post_crash: float = 0.05,
    custom_shock_pct: float = -35.0,
) -> Dict[str, Any]:
    """
    2. Sequence of Returns Risk (SRR) / Reverse Dollar-Cost Averaging Simulator.
    Evaluates what happens if a catastrophic crash hits in Years 1-3 of retirement.
    Compares selling equities at depressed bottoms vs using a Cash/Safe Asset buffer.
    """
    scenarios = {
        "great_depression_1929": {
            "name": "1929 Great Crash",
            "rates": [-0.30, -0.40, -0.20, 0.08, 0.15, 0.12, 0.09, 0.08, 0.07, 0.06],
            "desc": "Severe deflationary depression with consecutive catastrophic market declines.",
        },
        "stagflation_1973": {
            "name": "1973-1974 Stagflation",
            "rates": [-0.22, -0.28, 0.18, 0.12, -0.05, 0.04, 0.15, 0.05, 0.06, 0.05],
            "desc": "High inflation combined with consecutive negative real equity returns.",
        },
        "dot_com_2000": {
            "name": "2000 Dot-Com Bust",
            "rates": [-0.10, -0.13, -0.23, 0.26, 0.09, 0.04, 0.14, 0.05, -0.38, 0.23],
            "desc": "3-year consecutive tech collapse followed by the 2008 GFC.",
        },
        "gfc_2008": {
            "name": "2008 Global Financial Crisis",
            "rates": [-0.38, 0.23, 0.13, 0.01, 0.13, 0.29, 0.11, -0.01, 0.10, 0.19],
            "desc": "Liquidity freeze and 50%+ equity drop with sharp subsequent recovery.",
        },
        "custom": {
            "name": "Custom Sequence Shock",
            "rates": [custom_shock_pct / 100.0, -0.15, 0.04, 0.08, 0.06, 0.05, 0.05, 0.05, 0.05, 0.05],
            "desc": "Customized immediate bear market shock in Year 1.",
        },
    }

    scen = scenarios.get(crash_scenario, scenarios["stagflation_1973"])
    return_series = scen["rates"]

    # Sim 1: No safe buffer (selling equities directly at bottoms)
    bal_no_buffer = portfolio_val
    curve_no_buffer = []
    depleted_no_buffer_year = None

    for yr, r in enumerate(return_series, 1):
        bal_no_buffer = max(0.0, bal_no_buffer - annual_withdrawal)
        bal_no_buffer = round(bal_no_buffer * (1.0 + r), 2)
        curve_no_buffer.append({"year": yr, "return_pct": round(r * 100.0, 1), "balance": bal_no_buffer})
        if bal_no_buffer <= 0 and depleted_no_buffer_year is None:
            depleted_no_buffer_year = yr

    # Sim 2: Protected by safe asset buffer (draws from cash/GIC during negative years)
    bal_with_buffer = portfolio_val
    remaining_safe = safe_assets_val
    curve_with_buffer = []
    depleted_with_buffer_year = None
    safe_dollars_deployed = 0.0

    for yr, r in enumerate(return_series, 1):
        if r < 0 and remaining_safe > 0:
            # Draw from safe assets instead of equities!
            drawn = min(annual_withdrawal, remaining_safe)
            remaining_safe -= drawn
            safe_dollars_deployed += drawn
            equity_draw = annual_withdrawal - drawn
        else:
            equity_draw = annual_withdrawal

        bal_with_buffer = max(0.0, bal_with_buffer - equity_draw)
        bal_with_buffer = round(bal_with_buffer * (1.0 + r), 2)
        curve_with_buffer.append({
            "year": yr,
            "return_pct": round(r * 100.0, 1),
            "balance": bal_with_buffer,
            "safe_remaining": round(remaining_safe, 2),
        })
        if bal_with_buffer <= 0 and depleted_with_buffer_year is None:
            depleted_with_buffer_year = yr

    equity_capital_saved = round(max(0.0, bal_with_buffer - bal_no_buffer), 2)

    return {
        "scenario_key": crash_scenario,
        "scenario_name": scen["name"],
        "scenario_desc": scen["desc"],
        "initial_portfolio": round(portfolio_val, 2),
        "safe_assets_buffer": round(safe_assets_val, 2),
        "annual_withdrawal": round(annual_withdrawal, 2),
        "terminal_no_buffer": bal_no_buffer,
        "terminal_with_buffer": bal_with_buffer,
        "depleted_no_buffer_year": depleted_no_buffer_year,
        "depleted_with_buffer_year": depleted_with_buffer_year,
        "equity_capital_saved": equity_capital_saved,
        "safe_dollars_deployed": round(safe_dollars_deployed, 2),
        "curve_no_buffer": curve_no_buffer,
        "curve_with_buffer": curve_with_buffer,
    }


def calc_guyton_klinger_guardrails(
    portfolio_val: float,
    current_annual_withdrawal: float,
    initial_swr_pct: float = 4.0,
    inflation_rate: float = 0.025,
) -> Dict[str, Any]:
    """
    3. Guyton-Klinger Dynamic Guardrails Rules.
    - Capital Preservation Rule: If current withdrawal rate > initial_swr * 1.20, cut spending by 10%.
    - Prosperity Rule: If current withdrawal rate < initial_swr * 0.80, raise spending by 10%.
    """
    p_val = max(1.0, float(portfolio_val))
    draw = max(0.0, float(current_annual_withdrawal))
    init_swr = max(1.0, min(10.0, float(initial_swr_pct)))

    current_withdrawal_rate_pct = round((draw / p_val * 100.0), 2)
    upper_guardrail_pct = round(init_swr * 1.20, 2)
    lower_guardrail_pct = round(init_swr * 0.80, 2)

    upper_guardrail_dollars = round(p_val * (upper_guardrail_pct / 100.0), 2)
    lower_guardrail_dollars = round(p_val * (lower_guardrail_pct / 100.0), 2)

    if current_withdrawal_rate_pct > upper_guardrail_pct:
        rule_triggered = "capital_preservation"
        rule_desc = "Capital Preservation Rule Triggered: Current withdrawal rate exceeds the 120% upper guardrail. Trim spending by 10% to prevent portfolio depletion."
        recommended_withdrawal = round(draw * 0.90, 2)
        adjustment_pct = -10.0
    elif current_withdrawal_rate_pct < lower_guardrail_pct and draw > 0:
        rule_triggered = "prosperity"
        rule_desc = "Prosperity Rule Triggered: Current withdrawal rate is below the 80% lower guardrail. Portfolio has grown substantially; you can safely increase spending by 10%."
        recommended_withdrawal = round(draw * 1.10, 2)
        adjustment_pct = 10.0
    else:
        rule_triggered = "none"
        rule_desc = "Within Guardrails: Current withdrawal rate is within sustainable boundaries. Adjust spending purely for inflation."
        recommended_withdrawal = round(draw * (1.0 + inflation_rate), 2)
        adjustment_pct = round(inflation_rate * 100.0, 1)

    return {
        "portfolio_val": p_val,
        "current_annual_withdrawal": draw,
        "current_withdrawal_rate_pct": current_withdrawal_rate_pct,
        "initial_swr_pct": init_swr,
        "upper_guardrail_pct": upper_guardrail_pct,
        "lower_guardrail_pct": lower_guardrail_pct,
        "upper_guardrail_dollars": upper_guardrail_dollars,
        "lower_guardrail_dollars": lower_guardrail_dollars,
        "rule_triggered": rule_triggered,
        "rule_desc": rule_desc,
        "recommended_withdrawal": recommended_withdrawal,
        "adjustment_pct": adjustment_pct,
    }


def calc_three_bucket_architecture(
    total_wealth: float,
    annual_rle: float,
    current_safe_assets: float = 0.0,
    bucket1_years_target: float = 2.0,
    bucket2_years_target: float = 5.0,
) -> Dict[str, Any]:
    """
    4. Three-Bucket Retirement Runway Architecture:
      - Bucket 1: Liquid Cash, GIC, High-Interest Savings (1-3 years of RLE).
      - Bucket 2: Intermediate Bonds, Dividend Quality, Balanced ETFs (4-7 years of RLE).
      - Bucket 3: Long-Term Equity Growth (8+ years).
    """
    tot = max(0.0, float(total_wealth))
    rle = max(1.0, float(annual_rle))
    safe = min(tot, max(0.0, float(current_safe_assets)))

    b1_target = round(rle * bucket1_years_target, 2)
    b2_target = round(rle * bucket2_years_target, 2)
    b3_target = round(max(0.0, tot - b1_target - b2_target), 2)

    # Actual allocation: Safe assets go into Bucket 1 first, overflow into Bucket 2
    b1_actual = round(min(safe, b1_target), 2)
    overflow_safe = max(0.0, safe - b1_actual)
    b2_actual = round(min(overflow_safe, b2_target), 2)
    b3_actual = round(max(0.0, tot - safe), 2)

    b1_runway_months = round((b1_actual / (rle / 12.0)), 1)
    b2_runway_months = round((b2_actual / (rle / 12.0)), 1)
    total_safe_runway_years = round(((b1_actual + b2_actual) / rle), 1)

    b1_funded_pct = round(min(200.0, (b1_actual / b1_target * 100.0)), 1) if b1_target > 0 else 100.0
    b1_gap = round(max(0.0, b1_target - b1_actual), 2)

    return {
        "total_wealth": tot,
        "annual_rle": rle,
        "bucket1_name": "Bucket 1: Cash & Liquid Reserves",
        "bucket1_target": b1_target,
        "bucket1_actual": b1_actual,
        "bucket1_runway_months": b1_runway_months,
        "bucket1_funded_pct": b1_funded_pct,
        "bucket1_gap": b1_gap,
        "bucket2_name": "Bucket 2: Fixed Income & Defense",
        "bucket2_target": b2_target,
        "bucket2_actual": b2_actual,
        "bucket2_runway_months": b2_runway_months,
        "bucket3_name": "Bucket 3: Long-Term Equity Growth",
        "bucket3_target": b3_target,
        "bucket3_actual": b3_actual,
        "total_safe_runway_years": total_safe_runway_years,
    }


def calc_healthcare_ltc_contingency(
    portfolio_val: float,
    annual_ltc_cost: float = 60000.0,
    ltc_start_age: int = 83,
    ltc_duration_years: int = 4,
    current_age: int = 60,
    real_growth_rate: float = 0.04,
) -> Dict[str, Any]:
    """
    5. Healthcare & Long-Term Care (LTC) Contingency Shock Audit.
    Models whether the retiree's estate remains solvent during an end-of-life health shock.
    """
    cur_age = max(40, int(current_age))
    start_age = max(cur_age, int(ltc_start_age))
    dur = max(1, min(15, int(ltc_duration_years)))
    cost = max(0.0, float(annual_ltc_cost))
    total_nominal_ltc = round(cost * dur, 2)

    years_until_shock = max(0, start_age - cur_age)
    present_value_ltc = round(total_nominal_ltc / ((1.0 + real_growth_rate) ** years_until_shock), 2) if years_until_shock > 0 else total_nominal_ltc

    can_absorb = portfolio_val >= present_value_ltc
    ltc_wealth_impact_pct = round((present_value_ltc / portfolio_val * 100.0), 1) if portfolio_val > 0 else 100.0

    return {
        "current_age": cur_age,
        "ltc_start_age": start_age,
        "ltc_duration_years": dur,
        "annual_ltc_cost": cost,
        "total_ltc_cost": total_nominal_ltc,
        "present_value_needed": present_value_ltc,
        "can_absorb": can_absorb,
        "ltc_wealth_impact_pct": ltc_wealth_impact_pct,
    }


def calc_actuarial_longevity_table(
    current_age: int = 60,
    gender: str = "joint",
) -> Dict[str, Any]:
    """
    6. Empirical Actuarial Longevity Probabilities (Society of Actuaries / CDC Data).
    Calculates survival probabilities from current age to key milestones.
    """
    cur_age = max(30, min(95, int(current_age)))

    # Baseline probability of a 60-year-old surviving to age X
    # Male: 60->75: 78%, 80: 65%, 85: 48%, 90: 28%, 95: 11%, 100: 2%
    # Female: 60->75: 85%, 80: 74%, 85: 59%, 90: 38%, 95: 18%, 100: 4%
    # Joint (at least one surviving): 60->80: 91%, 85: 79%, 90: 55%, 95: 27%
    target_ages = [75, 80, 85, 90, 95, 100]
    results = []

    for ta in target_ages:
        if ta <= cur_age:
            p_male = 100.0
            p_fem = 100.0
            p_joint = 100.0
        else:
            diff = ta - cur_age
            # Empirical exponential mortality hazard rate formula
            hazard = 0.00035 * (1.095 ** ta)
            surv_single = max(1.0, min(99.0, 100.0 * (0.985 ** (diff * (1.0 + (ta - 60) * 0.03)))))
            p_male = round(surv_single * 0.90, 1)
            p_fem = round(min(99.0, surv_single * 1.05), 1)
            p_joint = round(100.0 - ((100.0 - p_male) * (100.0 - p_fem) / 100.0), 1)

        results.append({
            "target_age": ta,
            "prob_male": p_male,
            "prob_female": p_fem,
            "prob_joint": p_joint,
        })

    # Recommended 90th percentile longevity planning age
    recommended_planning_age = 95 if gender == "joint" else 92

    return {
        "current_age": cur_age,
        "gender": gender,
        "recommended_planning_age": recommended_planning_age,
        "longevity_schedule": results,
    }


def calc_monte_carlo_distribution(
    portfolio_val: float,
    annual_withdrawal: float,
    years: int = 30,
    mean_return: float = 0.065,
    std_dev: float = 0.12,
    num_trials: int = 500,
) -> Dict[str, Any]:
    """
    7. Monte Carlo 500-Trial Percentile Distribution (P10, P50, P90, Success Rate).
    Deterministic pseudo-random seed ensures reproducible and fast testing.
    """
    import random
    rng = random.Random(42)

    p_val = max(1.0, float(portfolio_val))
    draw = max(0.0, float(annual_withdrawal))
    sim_years = max(5, min(50, int(years)))

    successes = 0
    terminal_wealths = []

    for _ in range(num_trials):
        bal = p_val
        survived = True
        for yr in range(sim_years):
            bal -= draw
            if bal <= 0:
                bal = 0.0
                survived = False
                break
            # Normal distribution approximation
            shock = rng.gauss(mean_return, std_dev)
            bal *= (1.0 + shock)

        if survived:
            successes += 1
        terminal_wealths.append(round(bal, 2))

    terminal_wealths.sort()
    success_rate_pct = round((successes / num_trials * 100.0), 1)
    p10_idx = int(num_trials * 0.10)
    p50_idx = int(num_trials * 0.50)
    p90_idx = int(num_trials * 0.90)

    p10_wealth = terminal_wealths[p10_idx]
    p50_wealth = terminal_wealths[p50_idx]
    p90_wealth = terminal_wealths[p90_idx]

    return {
        "initial_portfolio": p_val,
        "annual_withdrawal": draw,
        "years": sim_years,
        "num_trials": num_trials,
        "success_rate_pct": success_rate_pct,
        "p10_terminal_wealth": p10_wealth,
        "p50_terminal_wealth": p50_wealth,
        "p90_terminal_wealth": p90_wealth,
    }


def calc_stagflation_sensitivity_matrix(
    portfolio_val: float,
    annual_withdrawal: float,
) -> Dict[str, Any]:
    """
    8. Inflation vs. Real Return Sensitivity Heat Matrix.
    Evaluates longevity duration (years) across a 4x4 matrix of Real Returns & Inflation.
    """
    p_val = max(1.0, float(portfolio_val))
    base_draw = max(1.0, float(annual_withdrawal))

    inflation_levels = [0.02, 0.035, 0.05, 0.07]
    real_returns = [0.01, 0.03, 0.05, 0.07]

    matrix = []
    for inf in inflation_levels:
        row = []
        for r_real in real_returns:
            # Simulate longevity in years
            bal = p_val
            draw = base_draw
            yr = 0
            while yr < 50 and bal > 0:
                yr += 1
                bal -= draw
                if bal <= 0:
                    break
                bal *= (1.0 + r_real)
                draw *= (1.0 + inf)

            row.append({
                "inflation_pct": round(inf * 100.0, 1),
                "real_return_pct": round(r_real * 100.0, 1),
                "longevity_years": yr if bal <= 0 else 50,
                "is_perpetual": bal > 0 and yr >= 50,
            })
        matrix.append(row)

    return {
        "base_withdrawal": base_draw,
        "portfolio_val": p_val,
        "matrix": matrix,
    }


def calc_rising_equity_glidepath(
    current_age: int = 60,
    retire_age: int = 60,
    current_equity_pct: float = 60.0,
) -> Dict[str, Any]:
    """
    9. Michael Kitces & Wade Pfau Rising Equity Glidepath Model.
    Counter-intuitively, beginning retirement at 40-50% equities and rising to 70%
    over the first 15 years substantially reduces Sequence of Returns Risk.
    """
    ret_age = max(40, int(retire_age))
    cur_age = max(30, int(current_age))
    years_in_retirement = max(0, cur_age - ret_age)

    # U-shaped glidepath: 50% at retirement, rising by 1.33%/yr to 70% at year 15
    if cur_age < ret_age:
        target_equity_pct = 65.0  # Accumulation phase
        phase_desc = "Accumulation Phase: Moderate-high growth equity stance"
    elif years_in_retirement <= 15:
        target_equity_pct = round(50.0 + (years_in_retirement * 1.33), 1)
        phase_desc = f"Rising Glidepath Phase (Year {years_in_retirement}/15): Defense against Sequence of Returns Risk"
    else:
        target_equity_pct = 70.0
        phase_desc = "Mature Retirement Phase: 70% Equity to defend against longevity inflation risk"

    deviation_pct = round(current_equity_pct - target_equity_pct, 1)

    return {
        "current_age": cur_age,
        "retire_age": ret_age,
        "years_in_retirement": years_in_retirement,
        "current_equity_pct": current_equity_pct,
        "target_equity_pct": target_equity_pct,
        "target_bond_pct": round(100.0 - target_equity_pct, 1),
        "deviation_pct": deviation_pct,
        "phase_desc": phase_desc,
    }




