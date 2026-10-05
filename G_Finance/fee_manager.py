"""
Portfolio Fee & Commission Manager
Handles fee structures, broker tariff presets (HSBC, CIBC, IBKR, Zero-Fee, Custom),
commission estimation (flat, percentage, minimum fees), and safe custody / storage fee tracking.
"""

import json
import os
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from csv_manager import (
    load_transactions,
    append_transaction,
    TRANSACTION_HISTORY_CSV,
    rotate_file_backups,
    DEFAULT_MAX_BACKUPS,
)

PORTFOLIO_FEES_FILE = "portfolio_fees.json"

# Pre-defined Broker Tariffs / Fee Presets
BROKER_PRESETS: Dict[str, Dict[str, Any]] = {
    "ZERO_COMMISSION": {
        "name_key": "preset_zero",
        "default_name": "Standard Zero-Commission (Robinhood / Schwab / Fidelity)",
        "name": "Standard Zero-Commission (Robinhood / Schwab / Fidelity)",
        "commission_type": "flat",  # flat, percent, percent_with_min, flat_plus_percent
        "commission_flat": 0.0,
        "commission_pct": 0.0,
        "commission_min": 0.0,
        "min_commission": 0.0,
        "storage_fee_amount": 0.0,
        "storage_fee_frequency": "none",  # monthly, semi-annually, annually, none
        "storage_fee_freq": "none",
        "default_tax_rate_pct": 0.0,
        "tax_rate": 0.0,
        "description": "$0 commission on US equities and ETFs, no custody or storage charges.",
        "notes": "$0 commission on US equities and ETFs, no custody or storage charges.",
    },
    "HSBC_STANDARD": {
        "name_key": "preset_hsbc_standard",
        "default_name": "HSBC Standard / Global (0.25%, min $15 / Safe Custody $5/mo)",
        "name": "HSBC Standard / Global (0.25%, min $15 / Safe Custody $5/mo)",
        "commission_type": "percent_with_min",
        "commission_flat": 0.0,
        "commission_pct": 0.25,
        "commission_min": 15.0,
        "min_commission": 15.0,
        "storage_fee_amount": 5.0,
        "storage_fee_frequency": "monthly",
        "storage_fee_freq": "monthly",
        "default_tax_rate_pct": 0.0,
        "tax_rate": 0.0,
        "description": "Standard HSBC retail tariff: 0.25% commission (min $15) and recurring monthly safe custody fee.",
        "notes": "Standard HSBC retail tariff: 0.25% commission (min $15) and recurring monthly safe custody fee.",
    },
    "HSBC_TRADE25": {
        "name_key": "preset_hsbc_trade25",
        "default_name": "HSBC Trade25 ($0 commission / HKD 25 monthly membership)",
        "name": "HSBC Trade25 ($0 commission / HKD 25 monthly membership)",
        "commission_type": "flat",
        "commission_flat": 0.0,
        "commission_pct": 0.0,
        "commission_min": 0.0,
        "min_commission": 0.0,
        "storage_fee_amount": 3.20,  # ~HKD 25
        "storage_fee_frequency": "monthly",
        "storage_fee_freq": "monthly",
        "default_tax_rate_pct": 0.0,
        "tax_rate": 0.0,
        "description": "HSBC Trade25 program: $0 commission per trade with a flat monthly membership / custody fee of HKD 25.",
        "notes": "HSBC Trade25 program: $0 commission per trade with a flat monthly membership / custody fee of HKD 25.",
    },
    "CIBC_INVESTOR": {
        "name_key": "preset_cibc",
        "default_name": "CIBC Imperial Investor / Investor's Edge ($6.95 flat / $25 quarterly admin)",
        "name": "CIBC Imperial Investor / Investor's Edge ($6.95 flat / $25 quarterly admin)",
        "commission_type": "flat",
        "commission_flat": 6.95,
        "commission_pct": 0.0,
        "commission_min": 6.95,
        "min_commission": 6.95,
        "storage_fee_amount": 25.0,
        "storage_fee_frequency": "semi-annually",
        "storage_fee_freq": "semi-annually",
        "default_tax_rate_pct": 0.0,
        "tax_rate": 0.0,
        "description": "CIBC online trading: $6.95 flat commission per stock/ETF trade, recurring account administration / custody fee.",
        "notes": "CIBC online trading: $6.95 flat commission per stock/ETF trade, recurring account administration / custody fee.",
    },
    "IBKR_FIXED": {
        "name_key": "preset_ibkr",
        "default_name": "Interactive Brokers (IBKR Fixed / $1.00 min)",
        "name": "Interactive Brokers (IBKR Fixed / $1.00 min)",
        "commission_type": "flat",
        "commission_flat": 1.0,
        "commission_pct": 0.0,
        "commission_min": 1.0,
        "min_commission": 1.0,
        "storage_fee_amount": 0.0,
        "storage_fee_frequency": "none",
        "storage_fee_freq": "none",
        "default_tax_rate_pct": 0.0,
        "tax_rate": 0.0,
        "description": "Low-cost electronic brokerage: $1.00 flat minimum per trade, $0 recurring custody fee.",
        "notes": "Low-cost electronic brokerage: $1.00 flat minimum per trade, $0 recurring custody fee.",
    },
    "CUSTOM": {
        "name_key": "preset_custom",
        "default_name": "Custom Tariff",
        "name": "Custom Tariff",
        "commission_type": "flat",
        "commission_flat": 0.0,
        "commission_pct": 0.0,
        "commission_min": 0.0,
        "min_commission": 0.0,
        "storage_fee_amount": 0.0,
        "storage_fee_frequency": "none",
        "storage_fee_freq": "none",
        "default_tax_rate_pct": 0.0,
        "tax_rate": 0.0,
        "description": "User-configured commission rates and custody storage fees.",
        "notes": "User-configured commission rates and custody storage fees.",
    },
}

DEFAULT_FEE_CONFIG: Dict[str, Any] = {
    "preset": "ZERO_COMMISSION",
    "commission_type": "flat",
    "commission_flat": 0.0,
    "commission_pct": 0.0,
    "commission_min": 0.0,
    "min_commission": 0.0,
    "storage_fee_amount": 0.0,
    "storage_fee_frequency": "none",
    "storage_fee_freq": "none",
    "default_tax_rate_pct": 0.0,
    "tax_rate": 0.0,
    "description": "",
    "notes": "",
    "last_storage_fee_date": "",
}


def get_preset_display_name(k: str) -> str:
    """Returns localized or default display name for a broker preset key."""
    p = BROKER_PRESETS.get(k, {})
    name_key = p.get("name_key", "")
    if name_key:
        try:
            from i18n import t
            val = t(name_key)
            if val and val != name_key:
                return val
        except Exception:
            pass
    return p.get("default_name") or p.get("name") or k


def load_all_portfolio_fees(filepath: str = PORTFOLIO_FEES_FILE) -> Dict[str, Any]:
    """Loads all portfolio fee configurations from JSON file."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception as e:
        print(f"Error loading portfolio fees from {filepath}: {e}")
        return {}


def save_all_portfolio_fees(fees_data: Dict[str, Any], filepath: str = PORTFOLIO_FEES_FILE) -> bool:
    """Saves all portfolio fee configurations with automatic backup."""
    if os.path.exists(filepath):
        rotate_file_backups(filepath, max_backups=DEFAULT_MAX_BACKUPS)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(fees_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving portfolio fees to {filepath}: {e}")
        return False


def get_portfolio_fee_config(portfolio_name: str, filepath: str = PORTFOLIO_FEES_FILE) -> Dict[str, Any]:
    """Retrieves fee configuration for a specific portfolio, defaulting to Zero Commission."""
    all_fees = load_all_portfolio_fees(filepath)
    if portfolio_name in all_fees:
        cfg = dict(DEFAULT_FEE_CONFIG)
        cfg.update(all_fees[portfolio_name])
        return cfg
    return dict(DEFAULT_FEE_CONFIG)


def save_portfolio_fee_config(portfolio_name: str, config: Dict[str, Any], filepath: str = PORTFOLIO_FEES_FILE) -> bool:
    """Saves or updates the fee configuration for a specific portfolio."""
    all_fees = load_all_portfolio_fees(filepath)
    clean_cfg = dict(DEFAULT_FEE_CONFIG)
    clean_cfg.update(config)
    all_fees[portfolio_name] = clean_cfg
    return save_all_portfolio_fees(all_fees, filepath)


def delete_portfolio_fee_config(portfolio_name: str, filepath: str = PORTFOLIO_FEES_FILE) -> bool:
    """Removes the fee configuration when a portfolio is deleted."""
    all_fees = load_all_portfolio_fees(filepath)
    if portfolio_name in all_fees:
        del all_fees[portfolio_name]
        return save_all_portfolio_fees(all_fees, filepath)
    return True


def rename_portfolio_fee_config(old_name: str, new_name: str, filepath: str = PORTFOLIO_FEES_FILE) -> bool:
    """Renames portfolio fee configuration key."""
    all_fees = load_all_portfolio_fees(filepath)
    if old_name in all_fees:
        all_fees[new_name] = all_fees.pop(old_name)
        return save_all_portfolio_fees(all_fees, filepath)
    return True


def calc_estimated_commission(
    portfolio_name: str,
    shares: float,
    price: float,
    action: str = "BUY",
    filepath: str = PORTFOLIO_FEES_FILE,
) -> float:
    """
    Calculates estimated broker commission based on the portfolio's configured tariff.
    Supports flat fees, percentages, minimum commission thresholds, or flat + percent combinations.
    """
    cfg = get_portfolio_fee_config(portfolio_name, filepath)
    shares = max(0.0, float(shares or 0.0))
    price = max(0.0, float(price or 0.0))
    trade_val = shares * price

    c_type = cfg.get("commission_type", "flat")
    flat_fee = float(cfg.get("commission_flat", 0.0) or 0.0)
    pct_rate = float(cfg.get("commission_pct", 0.0) or 0.0)
    min_fee = float(cfg.get("commission_min", 0.0) or 0.0)

    if trade_val <= 0:
        return 0.0

    if c_type == "flat":
        return round(flat_fee, 2)
    elif c_type == "percent":
        est = trade_val * (pct_rate / 100.0)
        return round(est, 2)
    elif c_type == "percent_with_min":
        est = trade_val * (pct_rate / 100.0)
        return round(max(min_fee, est), 2)
    elif c_type == "flat_plus_percent":
        est = flat_fee + (trade_val * (pct_rate / 100.0))
        return round(max(min_fee, est), 2)
    else:
        return round(flat_fee, 2)


def log_storage_fee_transaction(
    portfolio_name: str,
    amount: Optional[float] = None,
    fee_date: Optional[str] = None,
    notes: str = "",
    currency: str = "USD",
    filepath_tx: str = TRANSACTION_HISTORY_CSV,
    filepath_fees: str = PORTFOLIO_FEES_FILE,
) -> bool:
    """
    Logs a safe custody / storage fee as a dedicated FEE transaction in transaction_history.csv.
    Updates last_storage_fee_date in portfolio_fees.json.
    """
    cfg = get_portfolio_fee_config(portfolio_name, filepath_fees)
    fee_val = amount if amount is not None else float(cfg.get("storage_fee_amount", 0.0) or 0.0)
    if fee_val <= 0:
        return False

    dt_str = fee_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memo = notes or f"Safe Custody / Account Storage Fee ({cfg.get('storage_fee_frequency', 'monthly').capitalize()})"

    tx_record = {
        "date": dt_str,
        "type": "FEE",
        "portfolio": portfolio_name,
        "symbol": "—",
        "shares": 0.0,
        "price": 0.0,
        "total_amount": round(fee_val, 2),
        "cost_basis": 0.0,
        "commission_fee": round(fee_val, 2),
        "estimated_tax": 0.0,
        "net_amount": round(fee_val, 2),
        "net_profit": -round(fee_val, 2),
        "net_roi_pct": 0.0,
        "currency": currency,
        "notes": memo,
    }

    ok = append_transaction(tx_record, filepath_tx)
    if ok:
        cfg["last_storage_fee_date"] = dt_str[:10]
        save_portfolio_fee_config(portfolio_name, cfg, filepath_fees)
    return ok
