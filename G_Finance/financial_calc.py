"""
Financial Calculator Engine
Performs precise calculations for:
- Dividend income, yield on cost, quarterly/monthly projections
- Dividend Reinvestment (DRIP) multi-year compounding simulation
- Stock division / split adjustments (ratios e.g. 2:1, 4:1, 1:5)
- Selling calculations: gross proceeds, capital gains/loss, commissions, taxes, net profit, ROI
- Breakeven price and Target Profit price analysis
"""

from datetime import datetime, date
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
) -> Dict[str, Any]:
    """
    Comprehensive selling calculation:
    - Gross proceeds
    - Cost basis of sold shares
    - Broker fees / commission (flat + %)
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
    tax_rate_pct = max(0.0, float(tax_rate_pct))

    gross_proceeds = round(shares_to_sell * sell_price, 2)
    cost_basis = round(shares_to_sell * buy_price, 2)

    # Commission
    commission_fee = round(commission_flat + (gross_proceeds * commission_pct / 100.0), 2)

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
        "top_concentration_pct": top_concentration,
    }


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

