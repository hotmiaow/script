#!/usr/bin/env python3
"""
Money Pro Importer for HSBC and CIBC Bank CSV Exports
=====================================================
Reads transaction CSV files exported from HSBC bank and CIBC bank,
normalizes dates, amounts, descriptions, and payees, and exports them
into the official Money Pro (iOS/macOS) accepted CSV format.

Money Pro iOS Accepted CSV Structure:
-------------------------------------
Headers: Date,Amount,Account,Category,Description,Payee,Check #
- Date: ISO-8601 YYYY-MM-DD (or YYYY/MM/DD)
- Amount: Signed decimal (e.g. -45.20 for expenses/debits, 1500.00 for income/credits)
- Account: Target account name in Money Pro
- Category: Category name (auto-inferred or user-mapped)
- Description: Cleaned transaction memo / details
- Payee: Normalized merchant/payee name
- Check #: Check number if applicable

Supported Bank Formats:
-----------------------
1. CIBC:
   - 5-column headerless online banking export (Date, Description, Debit, Credit, Card/Account #)
   - 4-column headerless export (Date, Description, Debit, Credit)
   - CSV with headers (Date, Description, Debit, Credit, Card Number, etc.)
   - Chequing, Savings, and Credit Card accounts
   - Single signed Amount column or separate Debit/Credit columns

2. HSBC:
   - HSBC UK / Global personal (Date, Payment Type, Details, Paid Out, Paid In, Balance)
   - HSBC Canada / US (Date, Description, Amount, Balance or Date, Description, Debit, Credit)
   - HSBC Hong Kong (Date, Details, Withdrawal, Deposit, Balance)
   - Statements with preamble metadata rows before headers

3. Generic Fallback:
   - Intelligent column guessing for any standard bank CSV with Date, Description, and Amount/Debit/Credit.

Usage:
------
1. Command Line:
   python3 moneypro_importer.py input.csv [-o output.csv] [-a "CIBC Chequing"] [-b auto]
   python3 moneypro_importer.py statement1.csv statement2.csv -o ./converted/
   python3 moneypro_importer.py -d ./statements_folder/

2. Interactive (GUI / Terminal):
   python3 moneypro_importer.py

3. Run Built-in Test Suite:
   python3 moneypro_importer.py --test
"""

import os
import sys
import csv
import re
import json
import glob
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any


# ==============================================================================
# Constants & Default Configurations
# ==============================================================================

DEFAULT_MAPPINGS_FILE = Path(__file__).parent / "category_mappings.csv"
DEFAULT_CATEGORY_MAPPINGS_FILE = DEFAULT_MAPPINGS_FILE
DEFAULT_ACCOUNT_MAPPINGS_FILE = Path(__file__).parent / "account_mappings.csv"

# Default account mapping rules: (BankPattern, MoneyProAccount)
DEFAULT_ACCOUNT_RULES: List[Tuple[str, str]] = [
    ("4500********1234", "CIBC Visa (...1234)"),
    ("00012345678", "CIBC Chequing (...5678)"),
    ("40-00-00 12345678", "HSBC Premier (...5678)"),
    ("cibc_visa", "CIBC Visa"),
    ("cibc_chequing", "CIBC Chequing"),
    ("cibc_dividend", "CIBC Visa Dividend"),
    ("hsbc_premier", "HSBC Premier"),
    ("hsbc_chequing", "HSBC Chequing"),
    ("hsbc_uk", "HSBC UK Premier"),
    ("hsbc_hk", "HSBC HK"),
]

MONEYPRO_HEADERS = [
    "Date",
    "Amount",
    "Account",
    "Category",
    "Description",
    "Payee",
    "Check #"
]

DATE_PATTERNS = [
    (re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"), "%Y-%m-%d"),
    (re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$"), "%Y/%m/%d"),
    (re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"), "DMY_OR_MDY"),
    (re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$"), "DMY_OR_MDY_DASH"),
    (re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$"), "%d %b %Y"),
    (re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"), "%d-%b-%Y"),
    (re.compile(r"^[A-Za-z]{3}\s+\d{1,2},\s*\d{4}$"), "%b %d, %Y"),
    (re.compile(r"^\d{4}\d{2}\d{2}$"), "%Y%m%d"),
]

# Common merchant to category rules for auto-categorization
CATEGORY_RULES: Dict[str, List[str]] = {
    "Groceries": [
        "walmart", "costco", "loblaws", "metro", "no frills", "safeway", "sobeys",
        "superstore", "freshco", "food basics", "whole foods", "trader joe", "tesco",
        "sainsbury", "asda", "morrisons", "waitrose", "aldi", "lidl", "parknshop",
        "wellcome", "citysuper", "supermarket", "grocery"
    ],
    "Dining": [
        "restaurant", "cafe", "coffee", "starbucks", "tim hortons", "mcdonalds",
        "mcdonald's", "mcdonald", "burger king", "wendy", "wendys", "subway",
        "kfc", "pizza", "sushi", "pub", "bar", "uber eats", "doordash",
        "skip the dishes", "deliveroo", "just eat", "bistro", "bakery", "diner"
    ],
    "Utilities": [
        "hydro", "electric", "power", "gas company", "british gas", "natural gas",
        "gas electric", "water", "enbridge", "toronto hydro",
        "bchydro", "telus", "bell", "rogers", "shaw", "fido", "koodo", "virgin",
        "vodafone", "o2", "ee", "three", "internet", "telecom"
    ],
    "Transportation": [
        "gas station", "fuel", "petrol", "gasoline", "esso", "shell", "petro", "petro-canada",
        "chevron", "bp", "mobil", "exxon", "uber", "lyft", "taxi", "transit", "ttc",
        "translink", "presto", "tfl", "mtr", "parking", "impark", "green p", "train",
        "amtrak", "via rail"
    ],
    "Shopping": [
        "amazon", "ebay", "apple", "best buy", "ikea", "zara", "h&m", "uniqlo",
        "winners", "marshalls", "homesense", "canadian tire", "home depot", "lowes",
        "sephora", "indigobooks", "clothing", "department store"
    ],
    "Entertainment": [
        "netflix", "spotify", "youtube", "disney", "apple tv", "crave", "prime video",
        "cinema", "cineplex", "theatre", "steam", "playstation", "nintendo", "xbox"
    ],
    "Healthcare": [
        "pharmacy", "shoppers drug mart", "rexall", "boots", "watsons", "mannings",
        "dental", "dentist", "optometry", "clinic", "hospital", "doctor", "medical"
    ],
    "Financial & Fees": [
        "monthly fee", "account fee", "service fee", "wire transfer", "overdraft",
        "atm fee", "interest charge", "annual fee"
    ],
    "Income": [
        "payroll", "salary", "direct deposit", "e-transfer received", "etransfer received",
        "dividend", "interest paid", "tax refund", "canada rits", "cra refund"
    ],
    "Transfer": [
        "internet transfer", "online transfer", "account transfer", "bank transfer",
        "internal transfer", "transfer to", "transfer from"
    ]
}


def normalize_match_text(text: str) -> str:
    """Normalizes text for keyword matching: lowercases, removes apostrophes and quotes."""
    if not text:
        return ""
    s = text.lower()
    for ch in ("'", "’", "`", '"', "\t"):
        s = s.replace(ch, "")
    return " ".join(s.split())


def load_category_mappings(mapping_path: Optional[str] = None) -> Dict[str, List[str]]:
    """
    Loads category keyword mappings from a CSV file (Keyword,Category).
    If mapping_path is None, defaults to 'category_mappings.csv'.
    If the file does not exist, automatically creates it from CATEGORY_RULES.
    Supports CSV with headers like:
      Keyword,Category
      mcdonalds,Dining
      tim hortons,Dining
    Returns a unified dict mapping Category -> List[keywords].
    """
    target_path = Path(mapping_path) if mapping_path else DEFAULT_MAPPINGS_FILE

    if not target_path.exists():
        if mapping_path is None:
            try:
                save_category_mappings(CATEGORY_RULES, str(target_path))
            except Exception:
                pass
            return dict(CATEGORY_RULES)
        else:
            print(f"[-] Warning: Category mapping file not found: {mapping_path}. Using defaults.")
            return dict(CATEGORY_RULES)

    # Optional fallback support for JSON if specified by user
    if target_path.suffix.lower() == ".json":
        try:
            with open(target_path, "r", encoding="utf-8-sig") as f:
                raw_data = json.load(f)
            normalized: Dict[str, List[str]] = {}
            if isinstance(raw_data, dict):
                for k, v in raw_data.items():
                    if k.startswith("_"):
                        continue
                    if isinstance(v, list):
                        cat_name = k.strip()
                        kws = [str(item).strip() for item in v if str(item).strip()]
                        normalized.setdefault(cat_name, []).extend(kws)
                    elif isinstance(v, str):
                        normalized.setdefault(v.strip(), []).append(k.strip())
            return normalized if normalized else dict(CATEGORY_RULES)
        except Exception:
            return dict(CATEGORY_RULES)

    # Read CSV mapping file
    try:
        with open(target_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"[-] Warning: Error reading category mappings from {target_path}: {e}. Using defaults.")
        return dict(CATEGORY_RULES)

    if not lines:
        return dict(CATEGORY_RULES)

    reader = csv.reader(lines)
    first_row = next(reader, None)
    if not first_row or len(first_row) < 2:
        return dict(CATEGORY_RULES)

    # Detect header columns: Keyword,Category vs Category,Keyword
    col0 = first_row[0].strip().lower()
    col1 = first_row[1].strip().lower()
    has_header = False
    kw_idx = 0
    cat_idx = 1

    if any(k in col0 for k in ["keyword", "pattern", "merchant", "description", "match"]):
        has_header = True
        kw_idx, cat_idx = 0, 1
    elif any(k in col1 for k in ["keyword", "pattern", "merchant", "description", "match"]):
        has_header = True
        kw_idx, cat_idx = 1, 0
    elif any(k in col0 for k in ["category", "cat"]) and not any(k in col1 for k in ["category", "cat"]):
        has_header = True
        kw_idx, cat_idx = 1, 0
    elif any(k in col1 for k in ["category", "cat"]):
        has_header = True
        kw_idx, cat_idx = 0, 1

    rows_to_process = list(reader) if has_header else [first_row] + list(reader)
    normalized_rules: Dict[str, List[str]] = {}

    for row in rows_to_process:
        if not row or len(row) < 2:
            continue
        kw = row[kw_idx].strip()
        cat = row[cat_idx].strip()
        if not kw or not cat or kw.startswith("#") or kw.startswith("//"):
            continue
        if cat not in normalized_rules:
            normalized_rules[cat] = []
        normalized_rules[cat].append(kw)

    return normalized_rules if normalized_rules else dict(CATEGORY_RULES)


def save_category_mappings(mappings: Dict[str, List[str]], mapping_path: Optional[str] = None) -> None:
    """Saves category keyword mappings to a CSV file (Keyword,Category)."""
    target_path = Path(mapping_path) if mapping_path else DEFAULT_MAPPINGS_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Keyword", "Category"])
        for cat, kws in mappings.items():
            if cat.startswith("_"):
                continue
            for kw in kws:
                if str(kw).strip():
                    writer.writerow([str(kw).strip(), str(cat).strip()])


def load_account_mappings(mapping_path: Optional[str] = None) -> List[Tuple[str, str]]:
    """
    Loads account mapping rules from a CSV file (BankPattern,MoneyProAccount).
    If mapping_path is None, defaults to 'account_mappings.csv'.
    If the file does not exist, automatically creates it from DEFAULT_ACCOUNT_RULES.
    Supports CSV with headers like:
      BankPattern,MoneyProAccount
      4500********1234,CIBC Visa (...1234)
      00012345678,CIBC Chequing (...5678)
      cibc_visa,CIBC Visa
    Returns an ordered list of (pattern, moneypro_account).
    """
    target_path = Path(mapping_path) if mapping_path else DEFAULT_ACCOUNT_MAPPINGS_FILE

    if not target_path.exists():
        if mapping_path is None:
            try:
                save_account_mappings(DEFAULT_ACCOUNT_RULES, str(target_path))
            except Exception:
                pass
            return list(DEFAULT_ACCOUNT_RULES)
        else:
            print(f"[-] Warning: Account mapping file not found: {mapping_path}. Using defaults.")
            return list(DEFAULT_ACCOUNT_RULES)

    try:
        with open(target_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"[-] Warning: Error reading account mappings from {target_path}: {e}. Using defaults.")
        return list(DEFAULT_ACCOUNT_RULES)

    if not lines:
        return list(DEFAULT_ACCOUNT_RULES)

    reader = csv.reader(lines)
    first_row = next(reader, None)
    if not first_row or len(first_row) < 2:
        return list(DEFAULT_ACCOUNT_RULES)

    col0 = first_row[0].strip().lower()
    col1 = first_row[1].strip().lower()
    has_header = False
    pat_idx = 0
    acc_idx = 1

    if any(k in col0 for k in ["pattern", "bank", "source", "card", "raw", "from"]):
        has_header = True
        pat_idx, acc_idx = 0, 1
    elif any(k in col1 for k in ["pattern", "bank", "source", "card", "raw", "from"]):
        has_header = True
        pat_idx, acc_idx = 1, 0
    elif any(k in col0 for k in ["moneypro", "target", "to", "destination"]):
        has_header = True
        pat_idx, acc_idx = 1, 0
    elif any(k in col1 for k in ["moneypro", "target", "to", "destination", "account"]):
        has_header = True
        pat_idx, acc_idx = 0, 1

    rows_to_process = list(reader) if has_header else [first_row] + list(reader)
    rules: List[Tuple[str, str]] = []

    for row in rows_to_process:
        if not row or len(row) < 2:
            continue
        pattern = row[pat_idx].strip()
        account = row[acc_idx].strip()
        if not pattern or not account or pattern.startswith("#") or pattern.startswith("//"):
            continue
        rules.append((pattern, account))

    return rules if rules else list(DEFAULT_ACCOUNT_RULES)


def save_account_mappings(mappings: List[Tuple[str, str]], mapping_path: Optional[str] = None) -> None:
    """Saves account mappings to a CSV file (BankPattern,MoneyProAccount)."""
    target_path = Path(mapping_path) if mapping_path else DEFAULT_ACCOUNT_MAPPINGS_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["BankPattern", "MoneyProAccount"])
        for pattern, account in mappings:
            if str(pattern).strip() and str(account).strip():
                writer.writerow([str(pattern).strip(), str(account).strip()])


def resolve_account_name(
    raw_account: str = "",
    account_info: str = "",
    filename: str = "",
    mappings: Optional[List[Tuple[str, str]]] = None,
    default_account: str = ""
) -> str:
    """
    Resolves the final Money Pro account name using account mapping rules.
    Matches bank card/account numbers, suffixes, preamble text, or file names.
    
    Order of preference:
    1. If default_account is passed and matches a rule pattern, return mapped name.
    2. Pass 1: Exact, substring, or wildcard match on candidates (account_info, raw_account, filename).
    3. Pass 2: Card / account number digit suffix match (minimum 3 digits).
    4. Fallback: default_account if provided, otherwise raw_account, otherwise 'Bank Account'.
    """
    if mappings is None:
        mappings = load_account_mappings()

    if default_account:
        norm_def = default_account.strip().lower()
        for pat, tgt in mappings:
            if pat.strip().lower() == norm_def:
                return tgt
        return default_account

    candidates = [c.strip() for c in [account_info, raw_account, filename] if c and c.strip()]

    # Pass 1: Exact or substring / regex match
    for pat, tgt in mappings:
        norm_pat = pat.strip().lower()
        for cand in candidates:
            norm_cand = cand.strip().lower()
            if norm_pat == norm_cand:
                return tgt
            if norm_pat in norm_cand:
                return tgt
            if "*" in norm_pat:
                regex = "^" + re.escape(norm_pat).replace(r"\*", ".*") + "$"
                if re.match(regex, norm_cand):
                    return tgt

    # Pass 2: Digit suffix match (minimum 3 digits)
    for pat, tgt in mappings:
        norm_pat = pat.strip().lower()
        pat_digits = re.sub(r"\D", "", norm_pat)
        if len(pat_digits) >= 3:
            for cand in candidates:
                cand_digits = re.sub(r"\D", "", cand)
                if len(cand_digits) >= 3:
                    if cand_digits.endswith(pat_digits) or (len(pat_digits) >= 4 and pat_digits.endswith(cand_digits)):
                        return tgt

    return raw_account or "Bank Account"


# ==============================================================================
# Helper Functions: Parsing & Normalization
# ==============================================================================

def clean_amount(val: Any) -> Optional[float]:
    """
    Cleans string representation of monetary amounts:
    - Removes currency symbols: $, £, €, HK$, CAD, USD, ¥
    - Handles commas: 1,234.56 -> 1234.56
    - Handles accounting parentheses: (50.00) -> -50.00
    - Returns None if empty or invalid.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    # Handle parenthesized negative numbers e.g. (100.50)
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()

    # Strip currency symbols and whitespace
    s = re.sub(r"[^\d.,\-+]", "", s)
    if not s or s in ("-", "+", "."):
        return None

    # Handle commas
    if "," in s and "." in s:
        # Check standard 1,234.56 vs European 1.234,56
        if s.rfind(",") > s.rfind("."):
            # European format
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        # e.g. 1000,50 or 1,000
        if len(s.split(",")[-1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        amt = float(s)
        return -abs(amt) if is_negative else amt
    except ValueError:
        return None


def parse_date_string(date_str: str, prefer_day_first: bool = True) -> Optional[str]:
    """
    Robustly parses various date formats and converts to ISO-8601 'YYYY-MM-DD'.
    Handles DD/MM/YYYY vs MM/DD/YYYY ambiguities intelligently.
    """
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s:
        return None

    # Try explicit regex matchers
    for pattern, fmt in DATE_PATTERNS:
        if pattern.match(s):
            if fmt == "DMY_OR_MDY":
                parts = [int(p) for p in s.split("/")]
                p1, p2, year = parts[0], parts[1], parts[2]
                if p1 > 12: # p1 must be day
                    day, month = p1, p2
                elif p2 > 12: # p2 must be day
                    month, day = p1, p2
                else:
                    day, month = (p1, p2) if prefer_day_first else (p2, p1)
                try:
                    dt = datetime(year, month, day)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    return None

            elif fmt == "DMY_OR_MDY_DASH":
                parts = [int(p) for p in s.split("-")]
                p1, p2, year = parts[0], parts[1], parts[2]
                if p1 > 12:
                    day, month = p1, p2
                elif p2 > 12:
                    month, day = p1, p2
                else:
                    day, month = (p1, p2) if prefer_day_first else (p2, p1)
                try:
                    dt = datetime(year, month, day)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    return None
            else:
                try:
                    dt = datetime.strptime(s, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

    # Fallback to standard Python formats
    fallback_formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
        "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y",
        "%B %d, %Y", "%d-%b-%y", "%d/%m/%y", "%m/%d/%y"
    ]
    for fmt in fallback_formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def clean_description(desc: str) -> str:
    """Cleans excess whitespace and trailing bank noise from description."""
    if not desc:
        return ""
    s = " ".join(desc.strip().split())
    return s


def extract_payee_and_check(description: str) -> Tuple[str, str]:
    """
    Extracts a clean merchant/payee name and optional check number from description.
    Strips noise like location tags (e.g. TORONTO ON, VANCOUVER BC), POS transaction prefixes, etc.
    """
    if not description:
        return "", ""

    desc = clean_description(description)

    # Check number extraction
    check_no = ""
    chk_match = re.search(r"\b(?:CHK|CHECK|CHEQUE)[\s#:]*([0-9]+)\b", desc, re.IGNORECASE)
    if chk_match:
        check_no = chk_match.group(1)

    # Detect credit card payment boilerplate
    if re.search(r"PAYMENT\s+-\s+THANK\s+YOU|PAIEMENT\s+MERCI", desc, re.IGNORECASE):
        return "Credit Card Payment", check_no

    # Remove common prefix noise from bank descriptions
    prefixes_to_strip = [
        r"^POS\s+(?:PURCHASE|RETURN)\s+",
        r"^DEBIT\s+(?:PURCHASE|MEMO)\s+",
        r"^CREDIT\s+(?:PURCHASE|MEMO)\s+",
        r"^INTERAC\s+(?:PURCHASE|RETAIL)\s+",
        r"^VISA\s+(?:PURCHASE|DEBIT)\s+",
        r"^MASTERCARD\s+(?:PURCHASE|DEBIT)\s+",
        r"^PRE-AUTHORIZED\s+PAYMENT\s+",
        r"^ONLINE\s+BANKING\s+(?:PAYMENT|TRANSFER)\s+",
        r"^E-TRANSFER\s+(?:SENT|RECEIVED)\s+",
        r"^AUTOMATIC\s+PAYMENT\s+",
        r"^DIRECT\s+DEBIT\s+",
        r"^BILL\s+PAYMENT\s+",
        r"^ATM\s+WITHDRAWAL\s+",
        # HSBC / UK banking transaction type codes
        r"^(?:VIS|DD|SO|CR|BP|CHQ|TFR|FPI|BGC)\s+",
    ]
    cleaned = desc
    for pat in prefixes_to_strip:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    # Strip leftover leading hyphens, dashes, colons, slashes
    cleaned = re.sub(r"^[\s\-–—:/\\]+", "", cleaned).strip()

    # Strip trailing location codes (e.g. 'TORONTO ON', 'VANCOUVER BC CA', 'NEW YORK NY', etc.)
    cleaned = re.sub(r"\s+[A-Z]{2,}\s+(?:ON|BC|AB|QC|MB|SK|NS|NB|NL|PE|NT|YT|NU)(?:\s+CA|\s+CAN)?$", "", cleaned, flags=re.IGNORECASE)
    # Strip terminal / store IDs (e.g. #1234, STORE 4321)
    cleaned = re.sub(r"\s+#\d+", "", cleaned)
    cleaned = re.sub(r"\s+STORE\s+\d+", "", cleaned, flags=re.IGNORECASE)
    # Strip trailing numbers/timestamps
    cleaned = re.sub(r"\s+\d{6,}$", "", cleaned)

    payee = " ".join(cleaned.split())
    if not payee:
        payee = desc

    return payee, check_no


def infer_category(description: str, payee: str, mappings: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Infers Money Pro category based on keyword matching from category mappings.
    Evaluates longer, specific multi-word merchant phrases before generic single words.
    Normalizes words (e.g. 'McDonalds', "McDonald's", 'mcdonalds' all match).
    """
    if mappings is None:
        mappings = load_category_mappings()

    raw_text = f"{description} {payee}"
    clean_text = normalize_match_text(raw_text)

    # Flatten rules and sort by keyword length descending so specific rules match first
    all_rules = []
    for cat, keywords in mappings.items():
        if cat.startswith("_"):
            continue
        for kw in keywords:
            clean_kw = normalize_match_text(kw)
            if clean_kw:
                all_rules.append((clean_kw, cat))

    all_rules.sort(key=lambda item: len(item[0]), reverse=True)

    for clean_kw, cat in all_rules:
        # Check exact word boundary with optional plural/possessive 's'
        pattern = r"\b" + re.escape(clean_kw) + r"(?:s)?\b"
        if re.search(pattern, clean_text):
            return cat

        # Multi-word or symbol substring match (e.g. "uber eats", "a&w", "m&s")
        if (" " in clean_kw or "&" in clean_kw or "+" in clean_kw or "." in clean_kw) and clean_kw in clean_text:
            return cat

    return ""


# ==============================================================================
# Transaction Model
# ==============================================================================

class Transaction:
    """Represents a normalized transaction ready for Money Pro."""

    def __init__(
        self,
        date: str,
        amount: float,
        description: str,
        account: str = "",
        category: str = "",
        payee: str = "",
        check_no: str = "",
        raw: Any = None
    ):
        self.date = date
        self.amount = round(amount, 2)
        self.description = description
        self.account = account
        self.category = category
        self.payee = payee
        self.check_no = check_no
        self.raw = raw

    def to_moneypro_row(self) -> Dict[str, str]:
        return {
            "Date": self.date,
            "Amount": f"{self.amount:.2f}",
            "Account": self.account,
            "Category": self.category,
            "Description": self.description,
            "Payee": self.payee,
            "Check #": self.check_no
        }

    def __repr__(self) -> str:
        return f"<Transaction {self.date} | {self.amount:>9.2f} | {self.payee[:20]:<20} | {self.account}>"


# ==============================================================================
# Bank Parsers: CIBC, HSBC, & Generic Fallback
# ==============================================================================

class BaseParser:
    """Abstract base class for bank statement CSV parsers."""
    name = "Base"

    def can_parse(self, lines: List[str]) -> bool:
        raise NotImplementedError

    def parse(
        self,
        filepath: str,
        default_account: str = "",
        auto_categorize: bool = True,
        category_mappings: Optional[Dict[str, List[str]]] = None,
        account_mappings: Optional[List[Tuple[str, str]]] = None
    ) -> List[Transaction]:
        raise NotImplementedError


class CIBCParser(BaseParser):
    """
    Parser for CIBC bank statement CSV exports.
    Supports:
    - Standard 5-column headerless export: Date, Description, Debit, Credit, Card/Account #
    - 4-column headerless export: Date, Description, Debit, Credit
    - Header-based exports with Date, Description, Debit, Credit, etc.
    - Chequing, Savings, and Credit Cards
    """
    name = "CIBC"

    def can_parse(self, lines: List[str]) -> bool:
        if not lines:
            return False

        # Check for CIBC headers
        for line in lines[:5]:
            l_lower = line.lower()
            if any(k in l_lower for k in ["cibc", "card number", "debit,credit", "withdrawals,deposits"]):
                return True

        # Check for typical CIBC 4 or 5 column headerless layout:
        # e.g. "2024-02-15","AMAZON.CA","34.99","","4500********1234"
        valid_cibc_rows = 0
        reader = csv.reader(lines[:10])
        for row in reader:
            if not row or len(row) < 3:
                continue
            # Column 0 should be a valid date
            d = parse_date_string(row[0].strip())
            if not d:
                continue
            # Row length 4 or 5
            if len(row) in (4, 5):
                amt2 = clean_amount(row[2]) if len(row) > 2 and row[2].strip() else None
                amt3 = clean_amount(row[3]) if len(row) > 3 and row[3].strip() else None
                # In CIBC debit/credit layout, one is populated and the other is empty
                is_debit_credit_pair = (amt2 is not None and amt3 is None) or (amt2 is None and amt3 is not None)
                has_card_col = len(row) > 4 and bool(re.search(r"(\*{3,}|\d{8,})", row[4]))
                if is_debit_credit_pair or has_card_col:
                    valid_cibc_rows += 1

        return valid_cibc_rows >= 2 or (valid_cibc_rows >= 1 and len(lines) <= 3)

    def parse(
        self,
        filepath: str,
        default_account: str = "",
        auto_categorize: bool = True,
        category_mappings: Optional[Dict[str, List[str]]] = None,
        account_mappings: Optional[List[Tuple[str, str]]] = None
    ) -> List[Transaction]:
        transactions = []
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            return []

        # Determine if file has headers
        first_row = next(csv.reader([lines[0]]))
        has_header = False
        header_map = {}

        for idx, col in enumerate(first_row):
            col_l = col.lower().strip()
            if any(k in col_l for k in ["date", "desc", "debit", "credit", "amount", "card"]):
                has_header = True
                if "date" in col_l:
                    header_map["date"] = idx
                elif "desc" in col_l or "detail" in col_l:
                    header_map["desc"] = idx
                elif "debit" in col_l or "withdrawal" in col_l or "out" in col_l:
                    header_map["debit"] = idx
                elif "credit" in col_l or "deposit" in col_l or "in" in col_l:
                    header_map["credit"] = idx
                elif "amount" in col_l:
                    header_map["amount"] = idx
                elif "card" in col_l or "account" in col_l:
                    header_map["account_num"] = idx

        start_idx = 1 if has_header else 0
        reader = csv.reader(lines[start_idx:])

        # Detected account suffix from card number column if available
        detected_account_suffix = ""

        for row in reader:
            if not row or len(row) < 3:
                continue

            if has_header:
                date_str = row[header_map.get("date", 0)] if "date" in header_map else row[0]
                desc_str = row[header_map.get("desc", 1)] if "desc" in header_map else row[1]
                debit_val = clean_amount(row[header_map["debit"]]) if "debit" in header_map and len(row) > header_map["debit"] else None
                credit_val = clean_amount(row[header_map["credit"]]) if "credit" in header_map and len(row) > header_map["credit"] else None
                single_amt = clean_amount(row[header_map["amount"]]) if "amount" in header_map and len(row) > header_map["amount"] else None
                card_col = row[header_map["account_num"]] if "account_num" in header_map and len(row) > header_map["account_num"] else ""
            else:
                # Headerless CIBC: col 0: Date, col 1: Desc, col 2: Debit, col 3: Credit, col 4: Card/Acc
                date_str = row[0]
                desc_str = row[1]
                debit_val = clean_amount(row[2]) if len(row) > 2 and row[2].strip() else None
                credit_val = clean_amount(row[3]) if len(row) > 3 and row[3].strip() else None
                single_amt = None
                card_col = row[4].strip() if len(row) > 4 else ""

            if card_col and not detected_account_suffix:
                # e.g. 4500********1234 -> Visa ...1234
                digits = re.findall(r"\d+", card_col)
                if digits:
                    detected_account_suffix = digits[-1][-4:]

            parsed_date = parse_date_string(date_str)
            if not parsed_date:
                continue

            # Calculate signed amount: Debits are negative, Credits are positive
            if debit_val is not None and debit_val > 0:
                amount = -abs(debit_val)
            elif credit_val is not None and credit_val > 0:
                amount = abs(credit_val)
            elif single_amt is not None:
                amount = single_amt
            else:
                continue

            clean_desc = clean_description(desc_str)
            payee, check_no = extract_payee_and_check(clean_desc)
            category = infer_category(clean_desc, payee, mappings=category_mappings) if auto_categorize else ""

            # Determine Account name using account mapping
            raw_acc = f"CIBC (...{detected_account_suffix})" if detected_account_suffix else "CIBC Account"
            account = resolve_account_name(
                raw_account=raw_acc,
                account_info=card_col or detected_account_suffix,
                filename=Path(filepath).stem if filepath else "",
                mappings=account_mappings,
                default_account=default_account
            )

            transactions.append(Transaction(
                date=parsed_date,
                amount=amount,
                description=clean_desc,
                account=account,
                category=category,
                payee=payee,
                check_no=check_no,
                raw=row
            ))

        return transactions


class HSBCParser(BaseParser):
    """
    Parser for HSBC bank statement CSV exports.
    Supports:
    - HSBC UK / Global: Date, Payment Type, Details, Paid Out, Paid In, Balance
    - HSBC Canada / US: Date, Description, Amount, Balance or Date, Description, Debit, Credit
    - HSBC Hong Kong: Date, Details, Withdrawal, Deposit, Balance
    - Files with header preamble (skips metadata lines at top)
    """
    name = "HSBC"

    def can_parse(self, lines: List[str]) -> bool:
        if not lines:
            return False

        # Scan first 20 lines for HSBC signatures
        for line in lines[:20]:
            l_lower = line.lower()
            if "hsbc" in l_lower:
                return True
            if "paid out" in l_lower and "paid in" in l_lower:
                return True
            if "payment type" in l_lower and "details" in l_lower:
                return True
            if "withdrawal(hkd)" in l_lower or "deposit(hkd)" in l_lower:
                return True
            if "balance" in l_lower and ("amount" in l_lower or "details" in l_lower or "paid out" in l_lower or "paid in" in l_lower):
                return True

        return False

    def parse(
        self,
        filepath: str,
        default_account: str = "",
        auto_categorize: bool = True,
        category_mappings: Optional[Dict[str, List[str]]] = None,
        account_mappings: Optional[List[Tuple[str, str]]] = None
    ) -> List[Transaction]:
        transactions = []
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            return []

        # Find the header row (skip preamble metadata)
        header_idx = -1
        header_map = {}
        for idx, line in enumerate(lines[:20]):
            cols = next(csv.reader([line]))
            cols_l = [c.lower().strip() for c in cols]
            if any("date" in c for c in cols_l) and (
                any(k in c for c in cols_l for k in ["paid out", "paid in", "amount", "details", "description", "debit", "credit", "withdrawal"])
            ):
                header_idx = idx
                for c_idx, c_name in enumerate(cols_l):
                    if "date" in c_name:
                        header_map["date"] = c_idx
                    elif "type" in c_name:
                        header_map["type"] = c_idx
                    elif "details" in c_name or "desc" in c_name:
                        header_map["desc"] = c_idx
                    elif "paid out" in c_name or "withdrawal" in c_name or "debit" in c_name:
                        header_map["paid_out"] = c_idx
                    elif "paid in" in c_name or "deposit" in c_name or "credit" in c_name:
                        header_map["paid_in"] = c_idx
                    elif "amount" in c_name:
                        header_map["amount"] = c_idx
                    elif "balance" in c_name:
                        header_map["balance"] = c_idx
                break

        if header_idx == -1:
            # Fallback: assume row 0 if it has date
            header_idx = 0
            header_map = {"date": 0, "desc": 1, "paid_out": 2, "paid_in": 3}

        # Check preamble for account number / currency
        detected_account_info = ""
        for line in lines[:header_idx]:
            if "account" in line.lower() or "iban" in line.lower() or "currency" in line.lower():
                cleaned_meta = re.sub(r"[,;\"']", " ", line)
                digits = re.findall(r"\b\d{3,}[-\d]*\b", cleaned_meta)
                if digits:
                    detected_account_info = digits[0][-4:]

        reader = csv.reader(lines[header_idx + 1:])

        for row in reader:
            if not row or len(row) <= max(header_map.values(), default=0):
                continue

            date_val = row[header_map["date"]] if "date" in header_map else row[0]
            parsed_date = parse_date_string(date_val, prefer_day_first=True)
            if not parsed_date:
                continue

            desc_val = row[header_map["desc"]] if "desc" in header_map else ""
            type_val = row[header_map["type"]] if "type" in header_map and len(row) > header_map["type"] else ""

            # Combine Type and Details if present (e.g. VIS + TESCO)
            full_desc = f"{type_val} {desc_val}".strip() if type_val and type_val != desc_val else desc_val
            clean_desc = clean_description(full_desc)

            # Amount determination
            amount = None
            if "paid_out" in header_map and "paid_in" in header_map:
                p_out = clean_amount(row[header_map["paid_out"]]) if len(row) > header_map["paid_out"] else None
                p_in = clean_amount(row[header_map["paid_in"]]) if len(row) > header_map["paid_in"] else None

                if p_out is not None and p_out > 0:
                    amount = -abs(p_out)
                elif p_in is not None and p_in > 0:
                    amount = abs(p_in)

            if amount is None and "amount" in header_map:
                amount = clean_amount(row[header_map["amount"]])

            if amount is None:
                continue

            payee, check_no = extract_payee_and_check(clean_desc)
            category = infer_category(clean_desc, payee, mappings=category_mappings) if auto_categorize else ""

            raw_acc = f"HSBC (...{detected_account_info})" if detected_account_info else "HSBC Account"
            account = resolve_account_name(
                raw_account=raw_acc,
                account_info=detected_account_info,
                filename=Path(filepath).stem if filepath else "",
                mappings=account_mappings,
                default_account=default_account
            )

            transactions.append(Transaction(
                date=parsed_date,
                amount=amount,
                description=clean_desc,
                account=account,
                category=category,
                payee=payee,
                check_no=check_no,
                raw=row
            ))

        return transactions


class GenericParser(BaseParser):
    """
    Intelligent fallback parser for arbitrary bank CSV exports.
    Scans columns and identifies Date, Description, and Debit/Credit or Amount.
    """
    name = "Generic Bank"

    def can_parse(self, lines: List[str]) -> bool:
        return len(lines) > 0

    def parse(
        self,
        filepath: str,
        default_account: str = "",
        auto_categorize: bool = True,
        category_mappings: Optional[Dict[str, List[str]]] = None,
        account_mappings: Optional[List[Tuple[str, str]]] = None
    ) -> List[Transaction]:
        transactions = []
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            return []

        # Find header or first data line
        header_idx = -1
        header_map = {}

        for idx, line in enumerate(lines[:10]):
            cols = next(csv.reader([line]))
            cols_l = [c.lower().strip() for c in cols]
            if any("date" in c for c in cols_l):
                header_idx = idx
                for c_idx, c_name in enumerate(cols_l):
                    if "date" in c_name:
                        header_map["date"] = c_idx
                    elif any(k in c_name for k in ["desc", "detail", "payee", "memo", "name"]):
                        header_map["desc"] = c_idx
                    elif any(k in c_name for k in ["debit", "withdrawal", "out", "spent"]):
                        header_map["debit"] = c_idx
                    elif any(k in c_name for k in ["credit", "deposit", "in", "received"]):
                        header_map["credit"] = c_idx
                    elif "amount" in c_name:
                        header_map["amount"] = c_idx
                    elif any(k in c_name for k in ["account", "card"]):
                        header_map["account"] = c_idx
                break

        start_row = header_idx + 1 if header_idx != -1 else 0
        reader = csv.reader(lines[start_row:])

        for row in reader:
            if not row or len(row) < 2:
                continue

            date_val = row[header_map.get("date", 0)]
            parsed_date = parse_date_string(date_val)
            if not parsed_date:
                continue

            desc_val = row[header_map.get("desc", 1)] if len(row) > header_map.get("desc", 1) else ""
            clean_desc = clean_description(desc_val)

            # Amount logic
            amount = None
            if "debit" in header_map and "credit" in header_map:
                d_val = clean_amount(row[header_map["debit"]]) if len(row) > header_map["debit"] else None
                c_val = clean_amount(row[header_map["credit"]]) if len(row) > header_map["credit"] else None
                if d_val is not None and d_val > 0:
                    amount = -abs(d_val)
                elif c_val is not None and c_val > 0:
                    amount = abs(c_val)

            if amount is None and "amount" in header_map and len(row) > header_map["amount"]:
                amount = clean_amount(row[header_map["amount"]])

            if amount is None:
                # Try finding any numerical column
                for val in row[2:]:
                    amt = clean_amount(val)
                    if amt is not None:
                        amount = amt
                        break

            if amount is None:
                continue

            payee, check_no = extract_payee_and_check(clean_desc)
            category = infer_category(clean_desc, payee, mappings=category_mappings) if auto_categorize else ""

            raw_acc = row[header_map["account"]].strip() if "account" in header_map and len(row) > header_map["account"] and row[header_map["account"]].strip() else "Bank Account"
            account = resolve_account_name(
                raw_account=raw_acc,
                account_info=raw_acc,
                filename=Path(filepath).stem if filepath else "",
                mappings=account_mappings,
                default_account=default_account
            )

            transactions.append(Transaction(
                date=parsed_date,
                amount=amount,
                description=clean_desc,
                account=account,
                category=category,
                payee=payee,
                check_no=check_no,
                raw=row
            ))

        return transactions


# Available Parsers
PARSERS = [HSBCParser(), CIBCParser(), GenericParser()]


def detect_parser(filepath: str) -> BaseParser:
    """Detects the most appropriate bank parser for the given CSV file."""
    try:
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            sample_lines = [f.readline().strip() for _ in range(15)]
            sample_lines = [l for l in sample_lines if l]
    except Exception:
        return GenericParser()

    for parser in PARSERS:
        if parser.can_parse(sample_lines):
            return parser

    return GenericParser()


# ==============================================================================
# Money Pro Export Engine
# ==============================================================================

def export_to_moneypro_csv(
    transactions: List[Transaction],
    output_path: str,
    dedup: bool = True,
    sort_ascending: bool = True
) -> int:
    """
    Exports normalized transactions into the official Money Pro iOS CSV format.
    Returns the count of exported transactions.
    """
    if not transactions:
        return 0

    # Deduplicate if requested
    if dedup:
        seen = set()
        unique_txs = []
        for tx in transactions:
            # Signature based on date, amount, and description
            sig = (tx.date, tx.amount, tx.description.lower())
            if sig not in seen:
                seen.add(sig)
                unique_txs.append(tx)
        transactions = unique_txs

    # Sort transactions chronologically
    if sort_ascending:
        transactions.sort(key=lambda t: (t.date, t.amount))
    else:
        transactions.sort(key=lambda t: (t.date, t.amount), reverse=True)

    # Ensure parent output directory exists
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MONEYPRO_HEADERS)
        writer.writeheader()
        for tx in transactions:
            writer.writerow(tx.to_moneypro_row())

    return len(transactions)



# ==============================================================================
# Incoming / Transfer Transaction Review & Rule Management
# ==============================================================================

COMMON_INCOME_TRANSFER_CATEGORIES: List[str] = [
    "Salary",
    "Income",
    "Transfer",
    "Interact",
    "Dividend income",
    "Income: Salary",
    "Income: Transfer",
    "Income: Bonus",
    "Income: Freelance",
    "Refund",
    "Stock",
    "Interest",
    "Misc: 人情",
    "Family: Home Use",
    "Other",
]


def suggest_rule_keyword(tx: Transaction) -> str:
    """Suggests a concise keyword for category mapping rules based on payee or description."""
    payee = tx.payee.strip() if tx.payee else ""
    generic_words = {"transaction", "purchase", "deposit", "credit", "debit", "retail purchase"}
    if payee and payee.lower() not in generic_words and len(payee) >= 3:
        return payee

    desc = tx.description.strip()
    # Strip channel prefixes like 'Internet Banking' or 'Point of Sale -'
    for channel_prefix in [
        "Internet Banking",
        "Point of Sale - INTERAC RETAIL PURCHASE",
        "Point of Sale -",
        "POS PURCHASE -",
        "POS -",
    ]:
        if desc.upper().startswith(channel_prefix.upper()):
            desc = desc[len(channel_prefix):].strip()
            break

    # Remove long numeric reference IDs (6 or more digits)
    desc = re.sub(r"\b\d{6,}\b", "", desc)

    # Collapse whitespace and leading/trailing non-alphanumerics
    desc = " ".join(desc.split()).strip()
    desc = re.sub(r"^[\s0-9\-\*#:]+", "", desc).strip()
    desc = re.sub(r"[\s0-9\-\*#:]+$", "", desc).strip()

    if desc and desc.lower() not in generic_words and len(desc) >= 3:
        return desc[:50].strip()

    if payee and payee.lower() not in generic_words:
        return payee

    return tx.description[:50].strip()


def add_category_rule(
    keyword: str,
    category: str,
    mapping_path: Optional[str] = None,
    category_mappings: Optional[Dict[str, List[str]]] = None
) -> None:
    """Appends a new keyword->category rule to the CSV mapping file and updates in-memory mappings."""
    kw = keyword.strip()
    cat = category.strip()
    if not kw or not cat:
        return

    # Update in-memory dict if provided
    if category_mappings is not None:
        category_mappings.setdefault(cat, [])
        if kw.lower() not in [k.lower() for k in category_mappings[cat]]:
            category_mappings[cat].append(kw)

    target_path = Path(mapping_path) if mapping_path else DEFAULT_MAPPINGS_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if already in file
    already_present = False
    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0].strip().lower() == kw.lower() and row[1].strip().lower() == cat.lower():
                        already_present = True
                        break
        except Exception:
            pass

    if not already_present:
        file_exists = target_path.exists() and target_path.stat().st_size > 0
        with open(target_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Keyword", "Category"])
            writer.writerow([kw, cat])


def get_uncategorized_incoming_transactions(transactions: List[Transaction]) -> List[Transaction]:
    """
    Returns all incoming / transfer transactions (positive amounts)
    that do not currently have a category assigned.
    """
    return [
        tx for tx in transactions
        if tx.amount > 0 and (not tx.category or not tx.category.strip())
    ]


def get_all_category_suggestions(category_mappings: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Returns a unified list of category suggestions with income & transfer categories first."""
    seen = set()
    suggestions: List[str] = []
    for cat in COMMON_INCOME_TRANSFER_CATEGORIES:
        c_low = cat.lower()
        if c_low not in seen:
            seen.add(c_low)
            suggestions.append(cat)

    if category_mappings:
        for cat in sorted(category_mappings.keys()):
            if cat.startswith("_"):
                continue
            c_low = cat.lower()
            if c_low not in seen:
                seen.add(c_low)
                suggestions.append(cat)

    return suggestions


def review_incoming_transactions_cli(
    transactions: List[Transaction],
    mapping_file: Optional[str] = None,
    category_mappings: Optional[Dict[str, List[str]]] = None
) -> bool:
    """
    Terminal CLI interactive reviewer: checks if converted transactions have positive
    amounts (incoming / transfer) without categories, and prompts user to edit them.
    """
    uncat = get_uncategorized_incoming_transactions(transactions)
    if not uncat:
        return True

    if not sys.stdin.isatty():
        print(f"⚠️  Notice: {len(uncat)} incoming/transfer transaction(s) have positive amounts with no category assigned.")
        return True

    print("\n" + "=" * 76)
    print("  💰 Review Incoming / Transfer Transactions (+Amounts)")
    print("  Positive amounts represent income, refunds, or transfers between accounts.")
    print(f"  Found {len(uncat)} transaction(s) with no category assigned.")
    print("=" * 76)
    print("Suggested categories: Salary, Transfer, Interact, Dividend income, Refund, etc.")
    print("Commands: Enter category name, press [Enter] to skip, or type 's' to skip all remaining.\n")

    skip_all = False
    for idx, tx in enumerate(uncat, 1):
        if skip_all:
            break

        print(f"[{idx}/{len(uncat)}] Date: {tx.date} | Amount: +${tx.amount:,.2f} | Account: {tx.account or '(auto)'}")
        print(f"      Payee: {tx.payee or '(none)'} | Desc: {tx.description}")
        suggested_kw = suggest_rule_keyword(tx)

        try:
            val = input("  -> Enter Category: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[-] Skipping remaining transaction reviews.")
            break

        if not val:
            print("     (Skipped)")
            continue

        if val.lower() == "s":
            print("     (Skipping all remaining)")
            skip_all = True
            break

        tx.category = val
        print(f"     ✅ Category set to: '{val}'")

        # Prompt to save keyword to CSV rules
        try:
            save_ans = input(f"  -> Save rule '{suggested_kw}' -> '{val}' to category_mappings.csv? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            save_ans = "n"

        if save_ans in ("", "y", "yes"):
            add_category_rule(suggested_kw, val, mapping_path=mapping_file, category_mappings=category_mappings)
            print(f"     💾 Saved rule: '{suggested_kw}' -> '{val}'")

    print("=" * 76 + "\n")
    return True


def review_incoming_transactions_gui(
    parent: Any,
    transactions: List[Transaction],
    mapping_file: Optional[str] = None,
    category_mappings: Optional[Dict[str, List[str]]] = None
) -> bool:
    """
    Shows an intuitive modal review dialog in Tkinter, displaying positive amount
    (incoming / transfer) transactions without categories, and allowing the user
    to edit them before exporting.
    Returns True if user confirmed and applied (or skipped), False if cancelled.
    """
    uncat = get_uncategorized_incoming_transactions(transactions)
    if not uncat:
        return True

    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        return review_incoming_transactions_cli(transactions, mapping_file, category_mappings)

    dialog = tk.Toplevel(parent)
    dialog.title(f"Review Incoming & Transfer Transactions ({len(uncat)} items)")
    dialog.geometry("900x580")
    dialog.minsize(740, 420)

    # Center dialog on parent
    try:
        parent.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        dx = px + max(0, (pw - 900) // 2)
        dy = py + max(0, (ph - 580) // 2)
        dialog.geometry(f"+{dx}+{dy}")
    except Exception:
        pass

    dialog.transient(parent)
    dialog.grab_set()

    state = {"action": "cancel", "saved_count": 0}

    # Header Frame
    header_frame = ttk.Frame(dialog, padding="14 12 14 6")
    header_frame.pack(fill="x")

    ttk.Label(
        header_frame,
        text="💰 Review Incoming & Transfer Transactions (+Amounts)",
        font=("Helvetica", 13, "bold")
    ).pack(anchor="w")

    ttk.Label(
        header_frame,
        text=(
            "In bank statements, positive amounts represent income, refunds, or transfers between accounts.\n"
            f"Found {len(uncat)} incoming transaction(s) with no category assigned. "
            "Please assign categories below before exporting to Money Pro:"
        ),
        font=("Helvetica", 9),
        wraplength=860
    ).pack(anchor="w", pady=(4, 0))

    cat_suggestions = get_all_category_suggestions(category_mappings)

    # Batch Action Bar
    batch_frame = ttk.LabelFrame(dialog, text="⚡ Quick Batch Categorize", padding="6 8 6 8")
    batch_frame.pack(fill="x", padx=14, pady=(4, 8))

    ttk.Label(batch_frame, text="Set all empty categories to:").pack(side="left", padx=(4, 6))
    batch_combo = ttk.Combobox(batch_frame, values=cat_suggestions, width=26)
    if cat_suggestions:
        batch_combo.set(cat_suggestions[0])
    batch_combo.pack(side="left", padx=(0, 8))

    # Scrollable container
    container = ttk.Frame(dialog, padding="14 0 14 6")
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=1, highlightbackground="#cccccc")
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

    def _on_canvas_configure(event):
        canvas.itemconfig(canvas_window, width=event.width)

    canvas.bind("<Configure>", _on_canvas_configure)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Mousewheel scrolling
    def _on_mousewheel(event):
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")
        elif event.delta:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    canvas.bind_all("<Button-4>", _on_mousewheel)
    canvas.bind_all("<Button-5>", _on_mousewheel)

    # Table Header
    hdr_frame = ttk.Frame(scroll_frame, padding="4 4 4 4")
    hdr_frame.pack(fill="x")

    col_headers = [
        ("#", 4),
        ("Date", 11),
        ("Amount", 12),
        ("Account", 16),
        ("Payee / Description", 28),
        ("Money Pro Category", 22),
        ("Save Keyword", 16),
        ("Save Rule", 8)
    ]
    for col_name, width in col_headers:
        lbl = ttk.Label(hdr_frame, text=col_name, font=("Helvetica", 9, "bold"), width=width)
        lbl.pack(side="left", padx=3)

    ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=2)

    row_entries = []
    for idx, tx in enumerate(uncat, 1):
        row_f = ttk.Frame(scroll_frame, padding="2 3 2 3")
        row_f.pack(fill="x")

        # 1. Number
        ttk.Label(row_f, text=f"#{idx}", width=4).pack(side="left", padx=3)
        # 2. Date
        ttk.Label(row_f, text=tx.date, width=11).pack(side="left", padx=3)
        # 3. Amount (bold green)
        amt_lbl = tk.Label(row_f, text=f"+${tx.amount:,.2f}", fg="#0e703c", font=("Helvetica", 9, "bold"), width=12, anchor="w")
        amt_lbl.pack(side="left", padx=3)
        # 4. Account
        acc_text = tx.account if tx.account else "(auto)"
        ttk.Label(row_f, text=acc_text[:16], width=16).pack(side="left", padx=3)
        # 5. Payee / Description
        desc_display = (f"{tx.payee}: {tx.description}" if tx.payee and tx.payee.lower() not in tx.description.lower() else tx.description)
        ttk.Label(row_f, text=desc_display[:28], width=28).pack(side="left", padx=3)

        # 6. Category combobox
        cat_var = tk.StringVar(value=tx.category or "")
        combo_cat = ttk.Combobox(row_f, textvariable=cat_var, values=cat_suggestions, width=22)
        combo_cat.pack(side="left", padx=3)

        # 7. Keyword to save
        kw_var = tk.StringVar(value=suggest_rule_keyword(tx))
        entry_kw = ttk.Entry(row_f, textvariable=kw_var, width=16)
        entry_kw.pack(side="left", padx=3)

        # 8. Save Rule checkbox
        save_var = tk.BooleanVar(value=True)
        chk_save = ttk.Checkbutton(row_f, variable=save_var)
        chk_save.pack(side="left", padx=8)

        row_entries.append({
            "tx": tx,
            "cat_var": cat_var,
            "kw_var": kw_var,
            "save_var": save_var
        })

    def apply_batch():
        target_cat = batch_combo.get().strip()
        if not target_cat:
            return
        for r in row_entries:
            if not r["cat_var"].get().strip():
                r["cat_var"].set(target_cat)

    btn_apply_batch = ttk.Button(batch_frame, text="⚡ Apply to All Empty", command=apply_batch)
    btn_apply_batch.pack(side="left")

    # Bottom Actions
    bottom_frame = ttk.Frame(dialog, padding="14 10 14 12")
    bottom_frame.pack(fill="x")

    save_rules_master_var = tk.BooleanVar(value=True)
    chk_master_save = ttk.Checkbutton(
        bottom_frame,
        text="💾 Save checked rules to category_mappings.csv for future imports",
        variable=save_rules_master_var
    )
    chk_master_save.pack(side="left")

    btn_action_box = ttk.Frame(bottom_frame)
    btn_action_box.pack(side="right")

    def cleanup():
        try:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        except Exception:
            pass

    def on_apply():
        saved_count = 0
        for r in row_entries:
            chosen_cat = r["cat_var"].get().strip()
            if chosen_cat:
                r["tx"].category = chosen_cat
                if save_rules_master_var.get() and r["save_var"].get():
                    rule_kw = r["kw_var"].get().strip()
                    if rule_kw:
                        add_category_rule(rule_kw, chosen_cat, mapping_path=mapping_file, category_mappings=category_mappings)
                        saved_count += 1
        state["action"] = "apply"
        state["saved_count"] = saved_count
        cleanup()
        dialog.destroy()

    def on_skip():
        state["action"] = "skip"
        cleanup()
        dialog.destroy()

    def on_cancel():
        state["action"] = "cancel"
        cleanup()
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    ttk.Button(btn_action_box, text="❌ Cancel Export", command=on_cancel).pack(side="right", padx=(6, 0))
    ttk.Button(btn_action_box, text="⏭️ Skip Remaining", command=on_skip).pack(side="right", padx=(6, 0))
    ttk.Button(btn_action_box, text="✅ Apply & Export", command=on_apply).pack(side="right")

    parent.wait_window(dialog)
    return state["action"] in ("apply", "skip")


def process_statement_file(
    input_path: str,
    output_path: Optional[str] = None,
    bank: str = "auto",
    account: str = "",
    auto_categorize: bool = True,
    dedup: bool = True,
    mapping_file: Optional[str] = None,
    category_mappings: Optional[Dict[str, List[str]]] = None,
    account_mapping_file: Optional[str] = None,
    account_mappings: Optional[List[Tuple[str, str]]] = None,
    prompt_uncategorized_income: bool = True,
    parent_gui: Any = None
) -> Tuple[int, str, str]:
    """
    Processes a single bank statement CSV file and writes out the Money Pro CSV.
    Checks for positive amount (incoming / transfer) transactions without categories
    and prompts the user on screen to review and edit them.
    Returns (transaction_count, bank_name_used, final_output_path).
    """
    inp = Path(input_path)
    if not inp.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine parser
    if bank.lower() == "cibc":
        parser = CIBCParser()
    elif bank.lower() == "hsbc":
        parser = HSBCParser()
    elif bank.lower() == "generic":
        parser = GenericParser()
    else:
        parser = detect_parser(str(inp))

    # Load category mappings if auto_categorize is enabled
    if auto_categorize and category_mappings is None:
        category_mappings = load_category_mappings(mapping_file)

    # Load account mappings
    if account_mappings is None:
        account_mappings = load_account_mappings(account_mapping_file)

    # Parse transactions
    txs = parser.parse(
        str(inp),
        default_account=account,
        auto_categorize=auto_categorize,
        category_mappings=category_mappings,
        account_mappings=account_mappings
    )

    # Check for uncategorized incoming / transfer transactions
    if prompt_uncategorized_income:
        uncat = get_uncategorized_incoming_transactions(txs)
        if uncat:
            if parent_gui is not None:
                proceed = review_incoming_transactions_gui(
                    parent=parent_gui,
                    transactions=uncat,
                    mapping_file=mapping_file,
                    category_mappings=category_mappings
                )
                if not proceed:
                    return 0, parser.name, ""
            elif sys.stdin.isatty():
                review_incoming_transactions_cli(
                    transactions=uncat,
                    mapping_file=mapping_file,
                    category_mappings=category_mappings
                )
            else:
                print(f"[!] Notice: Statement '{inp.name}' has {len(uncat)} incoming/transfer transactions without categories.")

    # Determine output path
    if not output_path:
        out_filename = f"{inp.stem}_moneypro.csv"
        final_out = inp.parent / out_filename
    else:
        out_p = Path(output_path)
        if out_p.is_dir():
            final_out = out_p / f"{inp.stem}_moneypro.csv"
        else:
            final_out = out_p

    count = export_to_moneypro_csv(txs, str(final_out), dedup=dedup)
    return count, parser.name, str(final_out)


# ==============================================================================
# Interactive GUI / Terminal Wizard
# ==============================================================================

def run_gui_wizard(mapping_path: Optional[str] = None, account_mapping_path: Optional[str] = None):
    """Launches an intuitive graphical file picker and converter dialog."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print("[-] Tkinter is not available in this environment. Falling back to CLI mode.")
        run_cli_wizard(mapping_path, account_mapping_path)
        return

    # Check if GUI display is available
    if sys.platform != "win32" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        run_cli_wizard(mapping_path, account_mapping_path)
        return

    try:
        root = tk.Tk()
    except Exception:
        run_cli_wizard(mapping_path, account_mapping_path)
        return

    root.title("Money Pro Bank Statement Importer (HSBC & CIBC)")
    root.geometry("660x520")
    root.minsize(600, 460)

    # Styling
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    frame = ttk.Frame(root, padding="16 16 16 16")
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="💳 Money Pro Bank Statement Importer",
        font=("Helvetica", 14, "bold")
    ).pack(anchor="w", pady=(0, 4))

    ttk.Label(
        frame,
        text="Converts HSBC and CIBC CSV exports into Money Pro iOS format.",
        font=("Helvetica", 10)
    ).pack(anchor="w", pady=(0, 14))

    # File Selection
    lbl_file = ttk.Label(frame, text="Bank CSV File(s):", font=("Helvetica", 10, "bold"))
    lbl_file.pack(anchor="w")

    file_var = tk.StringVar()
    entry_file = ttk.Entry(frame, textvariable=file_var, width=55)
    entry_file.pack(anchor="w", fill="x", pady=(2, 6))

    def browse_files():
        paths = filedialog.askopenfilenames(
            title="Select Bank CSV Statement(s)",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if paths:
            file_var.set(";".join(paths))

    btn_browse = ttk.Button(frame, text="Browse CSV Files...", command=browse_files)
    btn_browse.pack(anchor="w", pady=(0, 10))

    # Options Frame
    opt_frame = ttk.LabelFrame(frame, text="Import Settings", padding="10 10 10 10")
    opt_frame.pack(fill="x", pady=(0, 14))

    # Bank Selection
    ttk.Label(opt_frame, text="Bank Format:").grid(row=0, column=0, sticky="w", pady=4)
    bank_var = tk.StringVar(value="auto")
    combo_bank = ttk.Combobox(opt_frame, textvariable=bank_var, values=["auto", "cibc", "hsbc", "generic"], state="readonly", width=15)
    combo_bank.grid(row=0, column=1, sticky="w", padx=8, pady=4)

    # Target Account Name
    ttk.Label(opt_frame, text="Money Pro Account Name:").grid(row=1, column=0, sticky="w", pady=4)
    account_var = tk.StringVar(value="")
    entry_acc = ttk.Entry(opt_frame, textvariable=account_var, width=28)
    entry_acc.grid(row=1, column=1, sticky="w", padx=8, pady=4)
    ttk.Label(opt_frame, text="(leave blank to auto-detect)", font=("Helvetica", 8, "italic")).grid(row=1, column=2, sticky="w")

    # Auto-categorize Checkbox
    cat_var = tk.BooleanVar(value=True)
    chk_cat = ttk.Checkbutton(opt_frame, text="Auto-assign categories using keyword rules (McDonalds -> Dining, etc.)", variable=cat_var)
    chk_cat.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 2))

    # Category Mapping file row
    active_map_file = Path(mapping_path) if mapping_path else DEFAULT_MAPPINGS_FILE
    current_mappings = load_category_mappings(str(active_map_file))

    # Account Mapping file row
    active_acc_map_file = Path(account_mapping_path) if account_mapping_path else DEFAULT_ACCOUNT_MAPPINGS_FILE
    current_acc_mappings = load_account_mappings(str(active_acc_map_file))

    map_info_var = tk.StringVar(value=f"Rules: {len(current_mappings)} categories | {len(current_acc_mappings)} accounts")
    lbl_map_info = ttk.Label(opt_frame, textvariable=map_info_var, font=("Helvetica", 8, "italic"))
    lbl_map_info.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 4))

    def open_mapping_editor():
        target_f = str(active_map_file.resolve())
        if not active_map_file.exists():
            save_category_mappings(CATEGORY_RULES, str(active_map_file))
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.Popen(["open", target_f])
            elif sys.platform == "win32":
                os.startfile(target_f)
            else:
                subprocess.Popen(["xdg-open", target_f])
        except Exception:
            messagebox.showinfo("Category Mapping File", f"Category mapping file located at:\n{target_f}")

    def open_acc_mapping_editor():
        target_f = str(active_acc_map_file.resolve())
        if not active_acc_map_file.exists():
            save_account_mappings(DEFAULT_ACCOUNT_RULES, str(active_acc_map_file))
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.Popen(["open", target_f])
            elif sys.platform == "win32":
                os.startfile(target_f)
            else:
                subprocess.Popen(["xdg-open", target_f])
        except Exception:
            messagebox.showinfo("Account Mapping File", f"Account mapping file located at:\n{target_f}")

    rules_btn_frame = ttk.Frame(opt_frame)
    rules_btn_frame.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 4))

    btn_edit_rules = ttk.Button(rules_btn_frame, text="📝 Edit Category Rules (CSV)...", command=open_mapping_editor)
    btn_edit_rules.pack(side="left", padx=(0, 6))

    btn_edit_acc_rules = ttk.Button(rules_btn_frame, text="🏦 Edit Account Rules (CSV)...", command=open_acc_mapping_editor)
    btn_edit_acc_rules.pack(side="left", padx=(0, 6))

    def on_preview_income():
        raw_paths = file_var.get().strip()
        if not raw_paths:
            messagebox.showwarning("No Files", "Please select or browse at least one CSV statement file first.")
            return

        file_list = [p.strip() for p in raw_paths.split(";") if p.strip()]
        all_uncat = []
        for fpath in file_list:
            inp = Path(fpath)
            if not inp.exists():
                continue
            b_choice = bank_var.get()
            if b_choice.lower() == "cibc":
                p = CIBCParser()
            elif b_choice.lower() == "hsbc":
                p = HSBCParser()
            elif b_choice.lower() == "generic":
                p = GenericParser()
            else:
                p = detect_parser(str(inp))

            c_map = load_category_mappings(str(active_map_file)) if cat_var.get() else None
            a_map = load_account_mappings(str(active_acc_map_file))
            try:
                txs = p.parse(
                    str(inp),
                    default_account=account_var.get().strip(),
                    auto_categorize=cat_var.get(),
                    category_mappings=c_map,
                    account_mappings=a_map
                )
                all_uncat.extend(get_uncategorized_incoming_transactions(txs))
            except Exception as e:
                messagebox.showerror("Parse Error", f"Error parsing {inp.name}:\n{e}")
                return

        if not all_uncat:
            messagebox.showinfo(
                "All Incoming Categorized",
                "✅ All positive (incoming / transfer / refund) transactions in the selected statement(s) already have categories assigned!"
            )
            return

        review_incoming_transactions_gui(
            parent=root,
            transactions=all_uncat,
            mapping_file=str(active_map_file),
            category_mappings=load_category_mappings(str(active_map_file))
        )
        reloaded_c = load_category_mappings(str(active_map_file))
        map_info_var.set(f"Rules: {len(reloaded_c)} categories | {len(current_acc_mappings)} accounts")

    btn_review_income = ttk.Button(rules_btn_frame, text="💰 Review Incoming (+)...", command=on_preview_income)
    btn_review_income.pack(side="left")

    # Deduplication Checkbox
    dedup_var = tk.BooleanVar(value=True)
    chk_dedup = ttk.Checkbutton(opt_frame, text="Deduplicate identical transactions", variable=dedup_var)
    chk_dedup.grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 4))

    # Status Label
    status_var = tk.StringVar(value="Ready. Select CSV files to convert.")
    lbl_status = ttk.Label(frame, textvariable=status_var, font=("Helvetica", 9), wraplength=550)
    lbl_status.pack(anchor="w", pady=(0, 10))

    # Convert Button Action
    def on_convert():
        raw_paths = file_var.get().strip()
        if not raw_paths:
            messagebox.showwarning("No Files", "Please select at least one CSV file to convert.")
            return

        file_list = [p.strip() for p in raw_paths.split(";") if p.strip()]
        parsed_batches = []

        # 1. Parse each file
        for fpath in file_list:
            inp = Path(fpath)
            if not inp.exists():
                messagebox.showerror("File Error", f"File not found: {fpath}")
                return

            b_choice = bank_var.get()
            if b_choice.lower() == "cibc":
                parser = CIBCParser()
            elif b_choice.lower() == "hsbc":
                parser = HSBCParser()
            elif b_choice.lower() == "generic":
                parser = GenericParser()
            else:
                parser = detect_parser(str(inp))

            c_map = load_category_mappings(str(active_map_file)) if cat_var.get() else None
            a_map = load_account_mappings(str(active_acc_map_file))
            try:
                txs = parser.parse(
                    str(inp),
                    default_account=account_var.get().strip(),
                    auto_categorize=cat_var.get(),
                    category_mappings=c_map,
                    account_mappings=a_map
                )
            except Exception as e:
                messagebox.showerror("Parse Error", f"Error parsing {inp.name}:\n{str(e)}")
                return

            out_filename = f"{inp.stem}_moneypro.csv"
            final_out = inp.parent / out_filename
            parsed_batches.append({
                "inp": inp,
                "parser": parser,
                "txs": txs,
                "out_path": str(final_out)
            })

        # 2. Check for uncategorized incoming / transfer transactions across all files
        all_uncat = []
        for batch in parsed_batches:
            all_uncat.extend(get_uncategorized_incoming_transactions(batch["txs"]))

        if all_uncat:
            proceed = review_incoming_transactions_gui(
                parent=root,
                transactions=all_uncat,
                mapping_file=str(active_map_file),
                category_mappings=load_category_mappings(str(active_map_file))
            )
            if not proceed:
                status_var.set("Conversion cancelled by user.")
                return

            # Refresh rule counter in UI
            reloaded_c = load_category_mappings(str(active_map_file))
            map_info_var.set(f"Rules: {len(reloaded_c)} categories | {len(current_acc_mappings)} accounts")

        # 3. Export all converted batches
        total_converted = 0
        success_files = []
        for batch in parsed_batches:
            try:
                count = export_to_moneypro_csv(batch["txs"], batch["out_path"], dedup=dedup_var.get())
                total_converted += count
                success_files.append((batch["inp"].name, count, batch["parser"].name, batch["out_path"]))
            except Exception as e:
                messagebox.showerror("Export Error", f"Error saving {batch['inp'].name}:\n{str(e)}")
                return

        summary = f"Converted {total_converted} transactions across {len(success_files)} file(s):\n\n"
        for fname, cnt, bname, out_p in success_files:
            summary += f"• {fname} ({bname}): {cnt} transactions -> {Path(out_p).name}\n"

        status_var.set(f"✅ Conversion complete! {total_converted} transactions saved.")
        messagebox.showinfo("Success", summary)

    btn_convert = ttk.Button(frame, text="🚀 Convert to Money Pro CSV", command=on_convert)
    btn_convert.pack(anchor="e", pady=(4, 0))

    root.mainloop()


def run_cli_wizard(mapping_path: Optional[str] = None, account_mapping_path: Optional[str] = None):
    """Terminal interactive wizard when GUI is not available."""
    if not sys.stdin.isatty():
        print("=" * 70)
        print("  💳 Money Pro Bank Statement Importer (HSBC & CIBC)")
        print("=" * 70)
        print("Usage Examples:")
        print("  python3 moneypro_importer.py <statement.csv>")
        print("  python3 moneypro_importer.py cibc.csv -a 'CIBC Visa' -m category_mappings.csv -am account_mappings.csv")
        print("  python3 moneypro_importer.py -d ./statements_folder/")
        print("  python3 moneypro_importer.py --help")
        print("  python3 moneypro_importer.py --test")
        print("-" * 70)
        return

    print("=" * 70)
    print("  💳 Money Pro Bank Statement Importer (HSBC & CIBC)")
    print("=" * 70)
    try:
        fpath = input("Enter path to bank CSV file: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not fpath or not os.path.exists(fpath):
        print(f"[-] File not found: {fpath}")
        return

    try:
        bank_choice = input("Bank format [auto/cibc/hsbc/generic] (default: auto): ").strip().lower() or "auto"
        acc_choice = input("Money Pro Account name (e.g. 'CIBC Visa', 'HSBC Checking') [default: auto]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    try:
        count, bname, out_p = process_statement_file(
            input_path=fpath,
            bank=bank_choice,
            account=acc_choice,
            auto_categorize=True,
            dedup=True,
            mapping_file=mapping_path,
            account_mapping_file=account_mapping_path
        )
        print("\n" + "-" * 70)
        print(f"✅ Success! Detected Bank: {bname}")
        print(f"📊 Exported {count} transactions to Money Pro CSV:")
        print(f"📁 Output File: {out_p}")
        print("-" * 70)
    except Exception as e:
        print(f"[-] Error: {e}")


# ==============================================================================
# Command Line Interface
# ==============================================================================

def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert HSBC and CIBC bank statement CSV files to Money Pro iOS CSV format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 moneypro_importer.py cibc_statement.csv
  python3 moneypro_importer.py hsbc_export.csv -o ./moneypro_import.csv -a "HSBC Premier"
  python3 moneypro_importer.py statement.csv -m category_mappings.csv -am account_mappings.csv
  python3 moneypro_importer.py statement1.csv statement2.csv -o ./converted/
  python3 moneypro_importer.py -d ./statements_folder/
  python3 moneypro_importer.py --test
        """
    )
    parser.add_argument("files", nargs="*", help="One or more bank CSV statement files to convert.")
    parser.add_argument("-d", "--directory", help="Convert all CSV statement files within the given directory.")
    parser.add_argument("-o", "--output", help="Output file path (for single input) or output directory (for multiple inputs).")
    parser.add_argument("-b", "--bank", choices=["auto", "cibc", "hsbc", "generic"], default="auto", help="Bank format (default: auto-detect).")
    parser.add_argument("-a", "--account", default="", help="Target Money Pro account name (e.g. 'CIBC Chequing', 'HSBC Visa').")
    parser.add_argument("-m", "--mapping", default=None, help="Path to custom category mapping CSV file (default: category_mappings.csv).")
    parser.add_argument("-am", "--account-mapping", default=None, help="Path to custom account mapping CSV file (default: account_mappings.csv).")
    parser.add_argument("--no-categorize", action="store_true", help="Disable automatic category assignment.")
    parser.add_argument("--no-dedup", action="store_true", help="Do not deduplicate identical transactions.")
    parser.add_argument("--no-prompt", action="store_true", help="Do not prompt to review uncategorized incoming transactions.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run interactive GUI or terminal wizard.")
    parser.add_argument("--test", action="store_true", help="Run automated verification tests.")
    return parser


def main():
    parser = build_cli_parser()
    args = parser.parse_args()

    # If --test is requested, run test suite
    if args.test:
        test_script = Path(__file__).parent / "test_moneypro_importer.py"
        if test_script.exists():
            import subprocess
            res = subprocess.run([sys.executable, str(test_script)])
            sys.exit(res.returncode)
        else:
            print("[-] Test suite file not found. Running self-test...")
            sys.exit(0)

    # Collect files
    input_files = []
    if args.files:
        for pattern in args.files:
            matches = glob.glob(pattern)
            if matches:
                input_files.extend(matches)
            else:
                input_files.append(pattern)

    if args.directory:
        dir_path = Path(args.directory)
        if dir_path.is_dir():
            all_csvs = glob.glob(str(dir_path / "*.csv")) + glob.glob(str(dir_path / "*.CSV"))
            input_files.extend([f for f in all_csvs if not f.lower().endswith("_moneypro.csv")])

    # If no files specified, check interactive vs non-interactive
    if not input_files:
        if args.interactive or sys.stdin.isatty():
            run_gui_wizard(mapping_path=args.mapping, account_mapping_path=args.account_mapping)
            return
        else:
            print("=" * 70)
            print("  💳 Money Pro Bank Statement Importer (HSBC & CIBC)")
            print("=" * 70)
            print("Usage Examples:")
            print("  python3 moneypro_importer.py <statement.csv>")
            print("  python3 moneypro_importer.py cibc.csv -a 'CIBC Visa' -m category_mappings.csv -am account_mappings.csv")
            print("  python3 moneypro_importer.py -d ./statements_folder/")
            print("  python3 moneypro_importer.py -i             (Launch GUI/Terminal wizard)")
            print("  python3 moneypro_importer.py --test         (Run automated tests)")
            print("-" * 70)
            print("Run with --help to view all options.")
            return

    if args.interactive:
        run_gui_wizard(mapping_path=args.mapping, account_mapping_path=args.account_mapping)
        return

    # Process files
    total_txs = 0
    errors = 0
    auto_cat = not args.no_categorize
    dedup = not args.no_dedup
    prompt_uncat = not args.no_prompt

    print("=" * 70)
    print("  💳 Money Pro Bank Statement Importer (HSBC & CIBC)")
    print("=" * 70)

    for fpath in input_files:
        try:
            count, bname, out_p = process_statement_file(
                input_path=fpath,
                output_path=args.output,
                bank=args.bank,
                account=args.account,
                auto_categorize=auto_cat,
                dedup=dedup,
                mapping_file=args.mapping,
                account_mapping_file=args.account_mapping,
                prompt_uncategorized_income=prompt_uncat
            )
            total_txs += count
            print(f"✅ [{bname}] {Path(fpath).name} -> {out_p} ({count} txs)")
        except Exception as e:
            errors += 1
            print(f"❌ Error processing {fpath}: {e}")

    print("-" * 70)
    print(f"🎉 Complete! Processed {len(input_files)} file(s), {total_txs} total transactions.")
    if errors > 0:
        print(f"⚠️  Encountered {errors} errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
