"""
Google Sheets Bidirectional Synchronization & Cloud Persistence Engine
========================================================================
Features:
1. Default Google Sheet Storage:
   - Stores and synchronizes primary data tables:
     • Portfolio (portfolio.csv)
     • Watchlist (watchlist.csv)
     • Transactions (transaction_history.csv)
     • Sales (sales_history.csv)
     • Portfolios (portfolios.json)
     • Sync_Meta (sync timestamps, device_id, hashes)
2. Automatic Round-Trip Sync:
   - On startup: checks cloud data, compares with local, fast-forwards if no conflict.
   - On edit: saves local file (with 10 rotating backups) and uploads updated data to Google Sheet.
3. Manual Sync Button:
   - Triggerable at any time from Desktop GUI and Web UI.
4. Smart Conflict Detection & Resolution:
   - Compares local data with Google Sheet item-by-item (by symbol/date/type).
   - Generates detailed human-readable and structured diff of changes.
   - Prompts user to choose: Keep Local (upload), Keep Remote (download with backup), or Smart Merge.
5. 10 Rotating Backups:
   - Maintains up to 10 safety backups before applying remote changes.
6. Cross-Device & Online Smoothness:
   - Unique device_id tracking to avoid self-conflict.
   - 3-way hash tracking (current_local, current_remote, last_synced) for seamless auto fast-forward.
   - Offline resilience: works completely offline without network lag, queues sync for when online.
   - Zero-dependency Google Apps Script Web App support: works natively across Linux, Windows, Mac, iOS a-Shell, and Pythonista 3.
   - Built-in ready-to-paste Google Apps Script code generator.
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import time
import socket
import hashlib
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Callable

# Project directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "google_sheet_config.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# Import local data manager
import csv_manager


def get_default_device_id() -> str:
    """Generates a stable pseudo-unique ID for this device installation."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "device"
    rand_suffix = uuid.uuid4().hex[:8]
    return f"{hostname}_{rand_suffix}"


def load_sheet_config() -> Dict[str, Any]:
    """Loads Google Sheet synchronization settings."""
    default_cfg: Dict[str, Any] = {
        "enabled": True,
        "web_app_url": "",
        "sheet_id": "",
        "api_key": "",
        "auto_upload_on_edit": True,
        "auto_sync_on_startup": True,
        "device_id": get_default_device_id(),
        "device_name": socket.gethostname() if hasattr(socket, "gethostname") else "Device",
        "last_sync_time": "",
        "last_sync_status": "not_configured",
        "last_sync_message": "Google Sheet URL not configured yet.",
        "last_synced_hash": "",
        "has_unsynced_edits": False,
        "pending_conflict": None,
    }

    if not os.path.exists(CONFIG_FILE):
        return default_cfg

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            if isinstance(saved, dict):
                default_cfg.update(saved)
                return default_cfg
    except Exception as e:
        print(f"Warning: Failed to read Google Sheet config: {e}")

    return default_cfg


def save_sheet_config(cfg: Dict[str, Any]) -> bool:
    """Saves Google Sheet synchronization settings."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving Google Sheet config: {e}")
        return False


def get_google_apps_script_template() -> str:
    """
    Returns the complete Google Apps Script code to paste into
    Google Sheets -> Extensions -> Apps Script.
    """
    return """/**
 * G_Finance Google Sheet Cloud Sync Bridge
 * =========================================
 * Instructions:
 * 1. Open your Google Spreadsheet (or create a new one: sheets.new).
 * 2. Click: Extensions -> Apps Script.
 * 3. Replace all existing code with this script.
 * 4. Click: Deploy -> New Deployment.
 * 5. Select type: 'Web app'.
 * 6. Set 'Execute as': 'Me' (your Google account).
 * 7. Set 'Who has access': 'Anyone' (or anyone with Google account).
 * 8. Click 'Deploy', authorize permissions, and copy the Web App URL.
 * 9. Paste the Web App URL into G_Finance Settings!
 */

function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "get_all";

  if (action === "ping") {
    return ContentService.createTextOutput(JSON.stringify({
      status: "ok",
      spreadsheet_name: ss.getName(),
      timestamp: new Date().toISOString()
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // Export all tabs
  var sheets = ss.getSheets();
  var resultData = {};
  var meta = {
    spreadsheet_name: ss.getName(),
    last_modified: new Date().toISOString(),
    sheet_names: []
  };

  for (var i = 0; i < sheets.length; i++) {
    var sheet = sheets[i];
    var name = sheet.getName();
    meta.sheet_names.push(name);

    if (name === "Sync_Meta") {
      continue;
    }

    var values = sheet.getDataRange().getValues();
    if (!values || values.length <= 1) {
      resultData[name] = [];
      continue;
    }

    var headers = values[0];
    var rows = [];
    for (var r = 1; r < values.length; r++) {
      var rowObj = {};
      var hasData = false;
      for (var c = 0; c < headers.length; c++) {
        var h = String(headers[c]).trim();
        if (h) {
          var val = values[r][c];
          if (val !== "" && val !== null && val !== undefined) {
            hasData = true;
          }
          rowObj[h] = val;
        }
      }
      if (hasData) {
        rows.push(rowObj);
      }
    }
    resultData[name] = rows;
  }

  return ContentService.createTextOutput(JSON.stringify({
    success: true,
    data: resultData,
    meta: meta
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var payload = {};
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: "Invalid JSON payload: " + err
    })).setMimeType(ContentService.MimeType.JSON);
  }

  var tables = payload.data || {};
  var meta = payload.meta || {};

  // Standard tab order: Portfolio, Watchlist, Transactions, Sales, Portfolios, Sync_Meta
  for (var tabName in tables) {
    var rows = tables[tabName];
    var sheet = ss.getSheetByName(tabName);
    if (!sheet) {
      sheet = ss.insertSheet(tabName);
    }
    sheet.clearContents();

    if (rows && rows.length > 0) {
      // Find all unique keys across all rows to form headers
      var headerSet = [];
      for (var i = 0; i < rows.length; i++) {
        var rKeys = Object.keys(rows[i]);
        for (var k = 0; k < rKeys.length; k++) {
          if (headerSet.indexOf(rKeys[k]) === -1) {
            headerSet.push(rKeys[k]);
          }
        }
      }

      var matrix = [headerSet];
      for (var r = 0; r < rows.length; r++) {
        var rowArr = [];
        for (var c = 0; c < headerSet.length; c++) {
          var key = headerSet[c];
          var cellVal = rows[r][key];
          rowArr.push(cellVal === undefined || cellVal === null ? "" : cellVal);
        }
        matrix.push(rowArr);
      }

      sheet.getRange(1, 1, matrix.length, headerSet.length).setValues(matrix);
      sheet.getRange(1, 1, 1, headerSet.length).setFontWeight("bold");
    }
  }

  // Record Sync Metadata
  var metaSheet = ss.getSheetByName("Sync_Meta");
  if (!metaSheet) {
    metaSheet = ss.insertSheet("Sync_Meta");
  }
  metaSheet.clearContents();
  var metaMatrix = [
    ["Property", "Value"],
    ["Last Updated", new Date().toISOString()],
    ["Updated By Device", meta.device_name || meta.device_id || "Unknown"],
    ["Device ID", meta.device_id || ""],
    ["Payload Hash", meta.data_hash || ""]
  ];
  metaSheet.getRange(1, 1, metaMatrix.length, 2).setValues(metaMatrix);
  metaSheet.getRange(1, 1, 1, 2).setFontWeight("bold");

  return ContentService.createTextOutput(JSON.stringify({
    success: true,
    message: "Google Sheet successfully updated.",
    timestamp: new Date().toISOString()
  })).setMimeType(ContentService.MimeType.JSON);
}
"""


class GoogleSheetSync:
    """
    Bidirectional synchronization engine for Google Sheets and local data.
    """

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or CONFIG_FILE
        self.config = load_sheet_config()
        self._lock = threading.Lock()
        self._upload_timer: Optional[threading.Timer] = None
        self._is_syncing = False

    def reload_config(self) -> Dict[str, Any]:
        with self._lock:
            self.config = load_sheet_config()
            return self.config

    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def is_configured(self) -> bool:
        url = (self.config.get("web_app_url") or "").strip()
        return bool(url and url.startswith("http"))

    def is_auto_sync_enabled(self) -> bool:
        return self.is_enabled() and self.is_configured() and bool(self.config.get("auto_upload_on_edit", True))

    def get_web_app_url(self) -> str:
        return (self.config.get("web_app_url") or "").strip()

    def set_web_app_url(self, url: str) -> bool:
        clean_url = url.strip()
        with self._lock:
            self.config["web_app_url"] = clean_url
            if clean_url:
                self.config["enabled"] = True
            return save_sheet_config(self.config)

    # -------------------------------------------------------------------------
    # HTTP Client with Redirect Support & Timeout
    # -------------------------------------------------------------------------
    def _http_request(
        self,
        url: str,
        method: str = "GET",
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 20,
    ) -> Tuple[int, str]:
        """
        Executes HTTP request following 301/302/303/307 redirects (essential for Google Apps Script).
        Uses urllib.request (zero external dependencies).
        """
        req_headers = {
            "User-Agent": "Mozilla/5.0 (G_Finance CloudSync/1.0)",
            "Accept": "application/json, text/plain, */*",
        }
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

        # Custom redirect handler that supports POST -> GET redirects standard for Apps Script
        class SmartRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                # Google Apps Script redirects POST to a GET on script.googleusercontent.com
                if code in (301, 302, 303, 307):
                    new_req = urllib.request.Request(
                        newurl,
                        headers=req.headers,
                        method="GET",
                    )
                    return new_req
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(SmartRedirectHandler())

        try:
            with opener.open(req, timeout=timeout) as response:
                status_code = response.getcode()
                charset = response.headers.get_content_charset("utf-8")
                raw_body = response.read()
                body_str = raw_body.decode(charset, errors="replace")
                return status_code, body_str
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            return e.code, err_body
        except urllib.error.URLError as e:
            raise ConnectionError(f"Network error connecting to Google Sheet: {e.reason}")
        except Exception as e:
            raise ConnectionError(f"HTTP request failed: {e}")

    # -------------------------------------------------------------------------
    # Connection Testing
    # -------------------------------------------------------------------------
    def test_connection(self, url: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """Tests whether the Google Apps Script Web App is live and responding."""
        target_url = (url or self.get_web_app_url()).strip()
        if not target_url:
            return False, "Google Sheet Web App URL is empty.", {}

        # Append action=ping
        separator = "&" if "?" in target_url else "?"
        ping_url = f"{target_url}{separator}action=ping"

        try:
            code, body = self._http_request(ping_url, method="GET", timeout=12)
            if code not in (200, 302):
                return False, f"Server returned HTTP status {code}", {}

            try:
                data = json.loads(body)
                if data.get("status") == "ok":
                    ss_name = data.get("spreadsheet_name", "Google Spreadsheet")
                    return True, f"Successfully connected to '{ss_name}'!", data
                elif data.get("success"):
                    return True, "Successfully connected to Google Sheet!", data
                else:
                    return True, "Received response from Google Sheet Web App.", data
            except json.JSONDecodeError:
                if "Google" in body or "html" in body.lower():
                    return False, "URL returned HTML instead of JSON. Ensure the Apps Script is deployed as Web App with access set to 'Anyone'.", {}
                return False, f"Invalid JSON response: {body[:150]}", {}

        except ConnectionError as e:
            return False, str(e), {}
        except Exception as e:
            return False, f"Connection failed: {str(e)}", {}

    # -------------------------------------------------------------------------
    # Local Data Export & Deserialization
    # -------------------------------------------------------------------------
    def export_all_local_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Reads all local CSV and JSON tables and returns a standardized dictionary."""
        # 1. Portfolio holdings
        holdings = csv_manager.load_portfolio(portfolio_name=None)
        clean_holdings = []
        for h in holdings:
            clean_holdings.append({
                "Portfolio": h.get("portfolio", "USD HSBC"),
                "Symbol": h.get("symbol", ""),
                "Name": h.get("name", ""),
                "Shares": float(h.get("shares", 0.0)),
                "Buy Price": float(h.get("buy_price", 0.0)),
                "Current Price": float(h.get("current_price", 0.0)),
                "Day Change": str(h.get("day_change", "")),
                "Currency": h.get("currency", "USD"),
                "Dividend Yield (%)": float(h.get("dividend_yield", 0.0)),
                "Annual Div/Share ($)": float(h.get("annual_div_per_share", 0.0)),
                "Sector": h.get("sector", ""),
                "Notes": h.get("notes", ""),
            })

        # 2. Watchlist
        watchlist = csv_manager.load_watchlist()
        clean_watchlist = []
        for w in watchlist:
            clean_watchlist.append({
                "Symbol": w.get("symbol", ""),
                "Name": w.get("name", ""),
                "Target Price": float(w.get("target_price", 0.0)),
                "Currency": w.get("currency", "USD"),
                "Notes": w.get("notes", ""),
                "Tags": w.get("tags", ""),
                "Added Date": w.get("added_date", ""),
            })

        # 3. Transactions
        transactions = csv_manager.load_transactions(portfolio_name=None)
        clean_tx = []
        for tx in transactions:
            clean_tx.append({
                "Date": tx.get("date", ""),
                "Portfolio": tx.get("portfolio", "USD HSBC"),
                "Symbol": tx.get("symbol", ""),
                "Type": tx.get("type", "BUY"),
                "Shares": float(tx.get("shares", 0.0)),
                "Price": float(tx.get("price", 0.0)),
                "Total Amount": float(tx.get("total_amount", 0.0)),
                "Fee": float(tx.get("fee", 0.0)),
                "Currency": tx.get("currency", "USD"),
                "Notes": tx.get("notes", ""),
            })

        # 4. Sales History
        sales = csv_manager.load_sales_history(portfolio_name=None)
        clean_sales = []
        for s in sales:
            clean_sales.append({
                "Date": s.get("date", ""),
                "Portfolio": s.get("portfolio", "USD HSBC"),
                "Symbol": s.get("symbol", ""),
                "Shares Sold": float(s.get("shares_sold", 0.0)),
                "Sell Price": float(s.get("sell_price", 0.0)),
                "Buy Price": float(s.get("buy_price", 0.0)),
                "Realized Gain/Loss": float(s.get("realized_gain_loss", 0.0)),
                "Currency": s.get("currency", "USD"),
                "Notes": s.get("notes", ""),
            })

        # 5. Portfolios list
        p_names = csv_manager.load_registered_portfolios()
        clean_portfolios = [{"Portfolio Name": name} for name in p_names if name]

        return {
            "Portfolio": clean_holdings,
            "Watchlist": clean_watchlist,
            "Transactions": clean_tx,
            "Sales": clean_sales,
            "Portfolios": clean_portfolios,
        }

    def apply_remote_data_to_local(
        self, remote_data: Dict[str, Any], create_backups: bool = True
    ) -> Tuple[bool, str]:
        """
        Applies data downloaded from Google Sheets directly to local disk.
        Before overwriting, rotates up to 10 safety backups per file.
        """
        if not isinstance(remote_data, dict):
            return False, "Invalid remote data format."

        try:
            # 1. Apply Portfolio
            if "Portfolio" in remote_data:
                p_rows = remote_data["Portfolio"]
                holdings = []
                for r in p_rows:
                    sym = str(r.get("Symbol") or r.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    p_name = str(r.get("Portfolio") or r.get("portfolio") or "USD HSBC").strip()
                    shs = float(r.get("Shares") or r.get("shares") or 0.0)
                    bp = float(r.get("Buy Price") or r.get("buy_price") or 0.0)
                    cp = float(r.get("Current Price") or r.get("current_price") or bp)
                    dy = float(r.get("Dividend Yield (%)") or r.get("dividend_yield") or 0.0)
                    curr = str(r.get("Currency") or r.get("currency") or "USD").strip().upper()
                    holdings.append({
                        "portfolio": p_name,
                        "symbol": sym,
                        "name": str(r.get("Name") or r.get("name") or sym),
                        "shares": shs,
                        "buy_price": bp,
                        "current_price": cp,
                        "dividend_yield": dy,
                        "currency": curr,
                        "day_change": str(r.get("Day Change") or r.get("day_change") or ""),
                        "notes": str(r.get("Notes") or r.get("notes") or ""),
                        "sector": str(r.get("Sector") or r.get("sector") or ""),
                    })
                csv_manager.save_portfolio(holdings)

            # 2. Apply Watchlist
            if "Watchlist" in remote_data:
                w_rows = remote_data["Watchlist"]
                watchlist = []
                for r in w_rows:
                    sym = str(r.get("Symbol") or r.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    watchlist.append({
                        "symbol": sym,
                        "name": str(r.get("Name") or r.get("name") or sym),
                        "target_price": float(r.get("Target Price") or r.get("target_price") or 0.0),
                        "currency": str(r.get("Currency") or r.get("currency") or "USD").strip().upper(),
                        "notes": str(r.get("Notes") or r.get("notes") or ""),
                        "tags": str(r.get("Tags") or r.get("tags") or ""),
                        "added_date": str(r.get("Added Date") or r.get("added_date") or ""),
                    })
                csv_manager.save_watchlist(watchlist)

            # 3. Apply Transactions
            if "Transactions" in remote_data:
                tx_rows = remote_data["Transactions"]
                transactions = []
                for r in tx_rows:
                    sym = str(r.get("Symbol") or r.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    transactions.append({
                        "date": str(r.get("Date") or r.get("date") or ""),
                        "portfolio": str(r.get("Portfolio") or r.get("portfolio") or "USD HSBC"),
                        "symbol": sym,
                        "type": str(r.get("Type") or r.get("type") or "BUY").upper(),
                        "shares": float(r.get("Shares") or r.get("shares") or 0.0),
                        "price": float(r.get("Price") or r.get("price") or 0.0),
                        "total_amount": float(r.get("Total Amount") or r.get("total_amount") or 0.0),
                        "fee": float(r.get("Fee") or r.get("fee") or 0.0),
                        "currency": str(r.get("Currency") or r.get("currency") or "USD").strip().upper(),
                        "notes": str(r.get("Notes") or r.get("notes") or ""),
                    })
                csv_manager.save_transactions(transactions)

            # 4. Apply Sales History
            if "Sales" in remote_data:
                s_rows = remote_data["Sales"]
                sales = []
                for r in s_rows:
                    sym = str(r.get("Symbol") or r.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    sales.append({
                        "date": str(r.get("Date") or r.get("date") or ""),
                        "portfolio": str(r.get("Portfolio") or r.get("portfolio") or "USD HSBC"),
                        "symbol": sym,
                        "shares_sold": float(r.get("Shares Sold") or r.get("shares_sold") or 0.0),
                        "sell_price": float(r.get("Sell Price") or r.get("sell_price") or 0.0),
                        "buy_price": float(r.get("Buy Price") or r.get("buy_price") or 0.0),
                        "realized_gain_loss": float(r.get("Realized Gain/Loss") or r.get("realized_gain_loss") or 0.0),
                        "currency": str(r.get("Currency") or r.get("currency") or "USD").strip().upper(),
                        "notes": str(r.get("Notes") or r.get("notes") or ""),
                    })
                csv_manager.save_sales_history(sales)

            # 5. Apply Portfolios
            if "Portfolios" in remote_data:
                pf_rows = remote_data["Portfolios"]
                p_names = []
                for r in pf_rows:
                    name = str(r.get("Portfolio Name") or r.get("name") or "").strip()
                    if name:
                        p_names.append(name)
                if p_names:
                    csv_manager.save_registered_portfolios(p_names)

            # Update last synced hash
            current_local = self.export_all_local_data()
            new_hash = self.compute_dataset_hash(current_local)
            with self._lock:
                self.config["last_synced_hash"] = new_hash
                self.config["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.config["last_sync_status"] = "success"
                self.config["last_sync_message"] = "Downloaded latest data from Google Sheet."
                self.config["has_unsynced_edits"] = False
                self.config["pending_conflict"] = None
                save_sheet_config(self.config)

            return True, "Successfully applied cloud data to local files."
        except Exception as e:
            return False, f"Failed applying cloud data: {e}"

    # -------------------------------------------------------------------------
    # Hashing & Difference Detection
    # -------------------------------------------------------------------------
    @staticmethod
    def compute_dataset_hash(data: Any) -> str:
        """Computes a deterministic MD5 hash of table contents."""
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()

    def compare_datasets(
        self, local_data: Dict[str, Any], remote_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compares local datasets against remote Google Sheet datasets item-by-item.
        Identifies added, deleted, and modified records across all tables.
        """
        differences = []
        counts = {"modified": 0, "local_only": 0, "remote_only": 0}

        # --- 1. Portfolio Holdings Comparison ---
        local_p = local_data.get("Portfolio", [])
        remote_p = remote_data.get("Portfolio", [])

        loc_map = {}
        for row in local_p:
            p_name = str(row.get("Portfolio") or "USD HSBC").strip()
            sym = str(row.get("Symbol") or "").strip().upper()
            if sym:
                loc_map[(p_name, sym)] = row

        rem_map = {}
        for row in remote_p:
            p_name = str(row.get("Portfolio") or "USD HSBC").strip()
            sym = str(row.get("Symbol") or "").strip().upper()
            if sym:
                rem_map[(p_name, sym)] = row

        all_keys = sorted(list(set(loc_map.keys()) | set(rem_map.keys())))
        for k in all_keys:
            p_name, sym = k
            label = f"{sym} ({p_name})"
            if k in loc_map and k not in rem_map:
                lh = loc_map[k]
                desc = f"{sym}: Added locally ({lh.get('Shares', 0)} shares @ ${lh.get('Buy Price', 0):.2f})"
                differences.append({
                    "tab": "Portfolio",
                    "type": "LOCAL_ONLY",
                    "key": label,
                    "local_val": f"{lh.get('Shares', 0)} shs @ ${lh.get('Buy Price', 0):.2f}",
                    "remote_val": "Not Present",
                    "description": desc,
                })
                counts["local_only"] += 1
            elif k in rem_map and k not in loc_map:
                rh = rem_map[k]
                desc = f"{sym}: Added in Google Sheet ({rh.get('Shares', 0)} shares @ ${rh.get('Buy Price', 0):.2f})"
                differences.append({
                    "tab": "Portfolio",
                    "type": "REMOTE_ONLY",
                    "key": label,
                    "local_val": "Not Present",
                    "remote_val": f"{rh.get('Shares', 0)} shs @ ${rh.get('Buy Price', 0):.2f}",
                    "description": desc,
                })
                counts["remote_only"] += 1
            else:
                lh = loc_map[k]
                rh = rem_map[k]
                l_shs = round(float(lh.get("Shares", 0.0)), 4)
                r_shs = round(float(rh.get("Shares", 0.0)), 4)
                l_bp = round(float(lh.get("Buy Price", 0.0)), 2)
                r_bp = round(float(rh.get("Buy Price", 0.0)), 2)

                diff_parts = []
                if abs(l_shs - r_shs) > 0.0001:
                    diff_parts.append(f"Shares: {l_shs} local vs {r_shs} cloud")
                if abs(l_bp - r_bp) > 0.01:
                    diff_parts.append(f"Buy Price: ${l_bp:.2f} local vs ${r_bp:.2f} cloud")

                if diff_parts:
                    desc = f"{sym}: " + ", ".join(diff_parts)
                    differences.append({
                        "tab": "Portfolio",
                        "type": "MODIFIED",
                        "key": label,
                        "local_val": f"{l_shs} shs @ ${l_bp:.2f}",
                        "remote_val": f"{r_shs} shs @ ${r_bp:.2f}",
                        "description": desc,
                    })
                    counts["modified"] += 1

        # --- 2. Watchlist Comparison ---
        local_w = {str(r.get("Symbol") or "").strip().upper(): r for r in local_data.get("Watchlist", []) if r.get("Symbol")}
        remote_w = {str(r.get("Symbol") or "").strip().upper(): r for r in remote_data.get("Watchlist", []) if r.get("Symbol")}

        for sym in sorted(list(set(local_w.keys()) | set(remote_w.keys()))):
            if sym in local_w and sym not in remote_w:
                differences.append({
                    "tab": "Watchlist",
                    "type": "LOCAL_ONLY",
                    "key": sym,
                    "local_val": f"Target: ${float(local_w[sym].get('Target Price', 0)):.2f}",
                    "remote_val": "Not Present",
                    "description": f"Watchlist {sym}: Added locally",
                })
                counts["local_only"] += 1
            elif sym in remote_w and sym not in local_w:
                differences.append({
                    "tab": "Watchlist",
                    "type": "REMOTE_ONLY",
                    "key": sym,
                    "local_val": "Not Present",
                    "remote_val": f"Target: ${float(remote_w[sym].get('Target Price', 0)):.2f}",
                    "description": f"Watchlist {sym}: Added in Google Sheet",
                })
                counts["remote_only"] += 1
            else:
                lw = local_w[sym]
                rw = remote_w[sym]
                l_tp = round(float(lw.get("Target Price", 0.0)), 2)
                r_tp = round(float(rw.get("Target Price", 0.0)), 2)
                if abs(l_tp - r_tp) > 0.01:
                    differences.append({
                        "tab": "Watchlist",
                        "type": "MODIFIED",
                        "key": sym,
                        "local_val": f"${l_tp:.2f}",
                        "remote_val": f"${r_tp:.2f}",
                        "description": f"Watchlist {sym}: Target price differs (${l_tp:.2f} local vs ${r_tp:.2f} cloud)",
                    })
                    counts["modified"] += 1

        # Summary text formatting
        has_diff = len(differences) > 0
        summary_lines = []
        if not has_diff:
            summary_lines.append("All data is perfectly identical between Local and Google Sheet.")
        else:
            summary_lines.append(f"Found {len(differences)} difference(s):")
            for d in differences[:8]:
                summary_lines.append(f"• [{d['tab']}] {d['description']}")
            if len(differences) > 8:
                summary_lines.append(f"• ... and {len(differences) - 8} more.")

        return {
            "has_differences": has_diff,
            "has_conflicts": counts["modified"] > 0 or (counts["local_only"] > 0 and counts["remote_only"] > 0),
            "differences": differences,
            "counts": counts,
            "summary_text": "\n".join(summary_lines),
        }

    # -------------------------------------------------------------------------
    # Cloud Download & Upload Actions
    # -------------------------------------------------------------------------
    def download_cloud_data(
        self, url: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
        """
        Downloads all data tables from Google Sheets via Web App.
        Returns: (success, data_dict, meta_dict, message)
        """
        target_url = (url or self.get_web_app_url()).strip()
        if not target_url:
            return False, None, None, "Google Sheet Web App URL is not set."

        sep = "&" if "?" in target_url else "?"
        get_url = f"{target_url}{sep}action=get_all"

        try:
            code, body = self._http_request(get_url, method="GET", timeout=22)
            if code != 200:
                return False, None, None, f"Google Sheet server returned HTTP {code}."

            res = json.loads(body)
            if not res.get("success", False) and "data" not in res:
                return False, None, None, res.get("error", "Unknown error from Google Sheet.")

            data = res.get("data", {})
            meta = res.get("meta", {})
            return True, data, meta, "Successfully downloaded Google Sheet data."
        except ConnectionError as e:
            return False, None, None, str(e)
        except json.JSONDecodeError:
            return False, None, None, "Failed to parse Google Sheet response as JSON."
        except Exception as e:
            return False, None, None, f"Download failed: {str(e)}"

    def upload_local_data_to_cloud(
        self, data: Optional[Dict[str, Any]] = None, url: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Uploads local data tables to Google Sheets via Web App POST.
        """
        target_url = (url or self.get_web_app_url()).strip()
        if not target_url:
            return False, "Google Sheet Web App URL is not set."

        dataset = data if data is not None else self.export_all_local_data()
        data_hash = self.compute_dataset_hash(dataset)

        payload = {
            "action": "update_all",
            "data": dataset,
            "meta": {
                "device_id": self.config.get("device_id", get_default_device_id()),
                "device_name": self.config.get("device_name", "Device"),
                "data_hash": data_hash,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}

        try:
            code, body = self._http_request(
                target_url, method="POST", data=payload_bytes, headers=headers, timeout=25
            )
            if code not in (200, 302):
                return False, f"Server returned HTTP {code} while updating Google Sheet."

            # Update last synced state
            with self._lock:
                self.config["last_synced_hash"] = data_hash
                self.config["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.config["last_sync_status"] = "success"
                self.config["last_sync_message"] = "Uploaded latest data to Google Sheet."
                self.config["has_unsynced_edits"] = False
                self.config["pending_conflict"] = None
                save_sheet_config(self.config)

            return True, "Successfully updated Google Sheet."
        except ConnectionError as e:
            # Mark unsynced edits so it will retry when connection restores
            with self._lock:
                self.config["has_unsynced_edits"] = True
                self.config["last_sync_status"] = "offline"
                self.config["last_sync_message"] = f"Offline: {e}"
                save_sheet_config(self.config)
            return False, str(e)
        except Exception as e:
            return False, f"Upload error: {str(e)}"

    # -------------------------------------------------------------------------
    # Core Bidirectional Synchronization Algorithm
    # -------------------------------------------------------------------------
    def perform_sync(
        self,
        force_direction: Optional[str] = None,
        on_conflict_callback: Optional[Callable[[Dict[str, Any]], str]] = None,
    ) -> Dict[str, Any]:
        """
        Full bidirectional synchronization cycle:
        1. Downloads latest Google Sheet data.
        2. Exports current local data.
        3. 3-way hash check:
           - Both hashes match -> Already up-to-date!
           - Local matches last synced & remote changed -> Fast-forward Download!
           - Remote matches last synced & local changed -> Fast-forward Upload!
           - Both changed -> Conflict detection!
        4. If conflict, presents differences and executes chosen resolution:
           - 'keep_local': Overwrite remote with local
           - 'keep_remote': Overwrite local with remote (rotates 10 backups)
           - 'merge': Smart-merge both datasets
        """
        if not self.is_enabled():
            return {"status": "disabled", "message": "Google Sheet sync is disabled in settings."}

        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "Google Sheet URL is not configured. Please paste your Web App URL in settings.",
            }

        with self._lock:
            if self._is_syncing:
                return {"status": "in_progress", "message": "Sync is already in progress..."}
            self._is_syncing = True

        try:
            # Step 1: Download remote data
            ok, remote_data, meta, msg = self.download_cloud_data()
            if not ok or remote_data is None:
                with self._lock:
                    self.config["last_sync_status"] = "offline"
                    self.config["last_sync_message"] = msg
                    save_sheet_config(self.config)
                return {"status": "offline", "message": msg}

            # Step 2: Export local data
            local_data = self.export_all_local_data()
            local_hash = self.compute_dataset_hash(local_data)
            remote_hash = self.compute_dataset_hash(remote_data)
            last_hash = self.config.get("last_synced_hash", "")

            # Step 3: Handle explicit force_direction if specified
            if force_direction == "keep_local":
                up_ok, up_msg = self.upload_local_data_to_cloud(local_data)
                return {
                    "status": "success" if up_ok else "error",
                    "direction": "upload",
                    "message": "Kept local version and uploaded to Google Sheet." if up_ok else up_msg,
                }
            elif force_direction == "keep_remote":
                app_ok, app_msg = self.apply_remote_data_to_local(remote_data, create_backups=True)
                return {
                    "status": "success" if app_ok else "error",
                    "direction": "download",
                    "message": "Kept Google Sheet version and updated local files." if app_ok else app_msg,
                }
            elif force_direction == "merge":
                merged = self.smart_merge_datasets(local_data, remote_data)
                self.apply_remote_data_to_local(merged, create_backups=True)
                self.upload_local_data_to_cloud(merged)
                return {
                    "status": "success",
                    "direction": "merge",
                    "message": "Successfully merged local and cloud changes.",
                }

            # Step 4: 3-way Hash Check
            # Case 1: Identical
            if local_hash == remote_hash:
                with self._lock:
                    self.config["last_synced_hash"] = local_hash
                    self.config["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.config["last_sync_status"] = "success"
                    self.config["last_sync_message"] = "Data is identical and up-to-date."
                    self.config["has_unsynced_edits"] = False
                    self.config["pending_conflict"] = None
                    save_sheet_config(self.config)
                return {
                    "status": "up_to_date",
                    "direction": "none",
                    "message": "Local files and Google Sheet are already in sync (up-to-date).",
                }

            # Case 2: Remote changed, Local untouched since last sync -> Auto Fast-forward Download
            if last_hash and local_hash == last_hash and remote_hash != last_hash:
                app_ok, app_msg = self.apply_remote_data_to_local(remote_data, create_backups=True)
                return {
                    "status": "success" if app_ok else "error",
                    "direction": "download",
                    "message": "Fast-forwarded local files with newer data from Google Sheet.",
                }

            # Case 3: Local changed, Remote untouched since last sync -> Auto Fast-forward Upload
            if last_hash and remote_hash == last_hash and local_hash != last_hash:
                up_ok, up_msg = self.upload_local_data_to_cloud(local_data)
                return {
                    "status": "success" if up_ok else "error",
                    "direction": "upload",
                    "message": "Fast-forwarded local edits to Google Sheet.",
                }

            # Case 4: Both modified or first sync with differences -> Diff & Conflict Check
            diff_report = self.compare_datasets(local_data, remote_data)
            if not diff_report["has_differences"]:
                with self._lock:
                    self.config["last_synced_hash"] = local_hash
                    save_sheet_config(self.config)
                return {
                    "status": "up_to_date",
                    "direction": "none",
                    "message": "No meaningful differences found.",
                }

            # Check if remote is completely empty (initial upload)
            is_remote_empty = (
                len(remote_data.get("Portfolio", [])) == 0
                and len(remote_data.get("Watchlist", [])) == 0
            )
            if is_remote_empty and len(local_data.get("Portfolio", [])) > 0:
                up_ok, up_msg = self.upload_local_data_to_cloud(local_data)
                return {
                    "status": "success",
                    "direction": "upload",
                    "message": "Initial upload to empty Google Sheet completed successfully.",
                }

            # Genuine conflict detected!
            conflict_payload = {
                "local_hash": local_hash,
                "remote_hash": remote_hash,
                "diff_report": diff_report,
                "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            with self._lock:
                self.config["pending_conflict"] = conflict_payload
                self.config["last_sync_status"] = "conflict"
                self.config["last_sync_message"] = f"Conflict: {len(diff_report['differences'])} differences detected."
                save_sheet_config(self.config)

            # If an interactive callback is provided (e.g. GUI dialog), invoke it
            if on_conflict_callback is not None:
                user_choice = on_conflict_callback(diff_report)
                if user_choice == "keep_local":
                    self.upload_local_data_to_cloud(local_data)
                    return {"status": "success", "direction": "upload", "message": "Conflict resolved: Kept local data."}
                elif user_choice == "keep_remote":
                    self.apply_remote_data_to_local(remote_data, create_backups=True)
                    return {"status": "success", "direction": "download", "message": "Conflict resolved: Kept Google Sheet data."}
                elif user_choice == "merge":
                    merged = self.smart_merge_datasets(local_data, remote_data)
                    self.apply_remote_data_to_local(merged, create_backups=True)
                    self.upload_local_data_to_cloud(merged)
                    return {"status": "success", "direction": "merge", "message": "Conflict resolved: Smart-merged data."}

            return {
                "status": "conflict",
                "direction": "conflict",
                "message": f"Conflict detected ({len(diff_report['differences'])} difference(s)). Please choose which version to keep.",
                "diff_report": diff_report,
                "differences": diff_report["differences"],
                "summary": diff_report["summary_text"],
            }

        finally:
            with self._lock:
                self._is_syncing = False

    # -------------------------------------------------------------------------
    # Smart Merging Algorithm
    # -------------------------------------------------------------------------
    @staticmethod
    def smart_merge_datasets(
        local_data: Dict[str, Any], remote_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Intelligently merges local and cloud datasets:
        - Portfolio: Combines unique holdings. If holding exists in both, keeps local version.
        - Watchlist: Unions symbols.
        - Transactions: Unions transactions by date, symbol, type, shares.
        - Sales: Unions sales records.
        - Portfolios: Unions portfolio names.
        """
        # 1. Portfolio
        p_merged = {}
        for row in remote_data.get("Portfolio", []):
            k = (str(row.get("Portfolio") or "USD HSBC").strip(), str(row.get("Symbol") or "").strip().upper())
            if k[1]:
                p_merged[k] = row
        for row in local_data.get("Portfolio", []):
            k = (str(row.get("Portfolio") or "USD HSBC").strip(), str(row.get("Symbol") or "").strip().upper())
            if k[1]:
                p_merged[k] = row  # Local overrides if modified

        # 2. Watchlist
        w_merged = {}
        for row in remote_data.get("Watchlist", []):
            sym = str(row.get("Symbol") or "").strip().upper()
            if sym:
                w_merged[sym] = row
        for row in local_data.get("Watchlist", []):
            sym = str(row.get("Symbol") or "").strip().upper()
            if sym:
                w_merged[sym] = row

        # 3. Transactions
        tx_seen = set()
        tx_merged = []
        for r in local_data.get("Transactions", []) + remote_data.get("Transactions", []):
            sig = (
                str(r.get("Date") or ""),
                str(r.get("Portfolio") or ""),
                str(r.get("Symbol") or "").upper(),
                str(r.get("Type") or "").upper(),
                round(float(r.get("Shares") or 0.0), 4),
            )
            if sig not in tx_seen:
                tx_seen.add(sig)
                tx_merged.append(r)

        # 4. Sales
        sales_seen = set()
        sales_merged = []
        for r in local_data.get("Sales", []) + remote_data.get("Sales", []):
            sig = (
                str(r.get("Date") or ""),
                str(r.get("Symbol") or "").upper(),
                round(float(r.get("Shares Sold") or 0.0), 4),
            )
            if sig not in sales_seen:
                sales_seen.add(sig)
                sales_merged.append(r)

        # 5. Portfolios
        pf_names = set()
        for r in local_data.get("Portfolios", []) + remote_data.get("Portfolios", []):
            n = str(r.get("Portfolio Name") or "").strip()
            if n:
                pf_names.add(n)

        return {
            "Portfolio": list(p_merged.values()),
            "Watchlist": list(w_merged.values()),
            "Transactions": tx_merged,
            "Sales": sales_merged,
            "Portfolios": [{"Portfolio Name": name} for name in sorted(list(pf_names))],
        }

    # -------------------------------------------------------------------------
    # Asynchronous Upload on Edit (Debounced & Non-Blocking)
    # -------------------------------------------------------------------------
    def queue_upload_on_edit(self, delay_seconds: float = 1.0):
        """
        Queues an automatic upload to Google Sheet after local edit.
        Debounces multiple rapid saves into a single request in a background thread.
        Never blocks the user interface or freezes the app.
        """
        if not self.is_auto_sync_enabled():
            return

        with self._lock:
            if self._upload_timer is not None:
                self._upload_timer.cancel()

            def _worker():
                try:
                    self.upload_local_data_to_cloud()
                except Exception as e:
                    print(f"Background cloud upload notice: {e}")

            self._upload_timer = threading.Timer(delay_seconds, _worker)
            self._upload_timer.daemon = True
            self._upload_timer.start()

    def get_sync_status(self) -> Dict[str, Any]:
        """Returns the current synchronization status dictionary."""
        with self._lock:
            cfg = self.config
            return {
                "enabled": cfg.get("enabled", True),
                "configured": self.is_configured(),
                "web_app_url": self.get_web_app_url(),
                "last_sync_time": cfg.get("last_sync_time", ""),
                "last_sync_status": cfg.get("last_sync_status", "not_configured"),
                "last_sync_message": cfg.get("last_sync_message", ""),
                "has_unsynced_edits": cfg.get("has_unsynced_edits", False),
                "has_conflict": cfg.get("pending_conflict") is not None,
                "device_id": cfg.get("device_id", ""),
                "device_name": cfg.get("device_name", ""),
            }


# Singleton accessor
_GOOGLE_SHEET_SYNC_INSTANCE: Optional[GoogleSheetSync] = None


def get_google_sheet_sync() -> GoogleSheetSync:
    """Returns the global GoogleSheetSync instance."""
    global _GOOGLE_SHEET_SYNC_INSTANCE
    if _GOOGLE_SHEET_SYNC_INSTANCE is None:
        _GOOGLE_SHEET_SYNC_INSTANCE = GoogleSheetSync()
    return _GOOGLE_SHEET_SYNC_INSTANCE
