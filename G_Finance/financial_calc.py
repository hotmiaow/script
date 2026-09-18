"""
Financial Calculator Engine
Performs precise calculations for:
- Dividend income, yield on cost, quarterly/monthly projections
- Dividend Reinvestment (DRIP) multi-year compounding simulation
- Stock division / split adjustments (ratios e.g. 2:1, 4:1, 1:5)
- Selling calculations: gross proceeds, capital gains/loss, commissions, taxes, net profit, ROI
- Breakeven price and Target Profit price analysis
"""

from typing import Dict, Any, List


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

    allocations = []
    best_holding = None
    worst_holding = None

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

        unrealized_pct = float(h.get("unrealized_gain_pct", 0.0))
        if best_holding is None or unrealized_pct > float(best_holding.get("unrealized_gain_pct", -999999)):
            best_holding = h
        if worst_holding is None or unrealized_pct < float(worst_holding.get("unrealized_gain_pct", 999999)):
            worst_holding = h

        allocations.append({
            "symbol": str(h.get("symbol", "")),
            "name": str(h.get("name", "")),
            "value_base": round(mkt_val, 2),
            "currency": curr,
            "rate_used": rate,
        })

    for a in allocations:
        a["weight_pct"] = round((a["value_base"] / total_value * 100), 2) if total_value > 0 else 0.0

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
