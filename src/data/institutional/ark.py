# src/data/institutional/ark.py
from __future__ import annotations

import os
import time
from io import StringIO
from typing import Dict, Optional
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from src.data.utils import safe_fetch

# Throttle repeated "unavailable" logs per ETF
_LAST_LOG: Dict[str, float] = {}
def _once_per(etf: str, secs: float) -> bool:
    now = time.time()
    last = _LAST_LOG.get(etf, 0.0)
    if now - last >= secs:
        _LAST_LOG[etf] = now
        return True
    return False

# Updated CSV endpoints based on current ARK structure
CSV_CANDIDATES = {
    "ARKK": [
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
        "https://www.ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    ],
    "ARKW": [
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
        "https://www.ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    ],
    "ARKQ": [
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_AUTONOMOUS_TECHNOLOGY_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
        "https://www.ark-funds.com/wp-content/uploads/funds-etf-csv/ARKQ_holdings.csv",
    ],
    "ARKG": [
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
        "https://www.ark-funds.com/wp-content/uploads/funds-etf-csv/ARKG_holdings.csv",
    ],
    "ARKF": [
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv",
        "https://www.ark-funds.com/wp-content/uploads/funds-etf-csv/ARKF_holdings.csv",
    ],
    "ARKX": [
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_SPACE_EXPLORATION_INNOVATION_ETF_ARKX_HOLDINGS.csv",
    ],
}

# Cache to keep you running even if ARK blocks later
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".market_twin_cache", "ark")
os.makedirs(CACHE_DIR, exist_ok=True)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/csv;q=0.8,*/*;q=0.7",
    "Referer": "https://www.ark-funds.com/",
    "Origin": "https://www.ark-funds.com",
    "Connection": "keep-alive",
}

def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.6,
        status_forcelist=(403, 408, 409, 429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update(BROWSER_HEADERS)
    return s

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ticker", "weight (%)"])
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    # Standardize → ticker
    ticker_col = None
    for c in ("ticker", "ticker symbol", "ticker_symbol", "holding ticker", "symbol"):
        if c in df.columns:
            ticker_col = c
            break
    # Standardize → weight (%)
    weight_col = None
    for c in ("weight (%)", "weight %", "weight", "portfolio weight"):
        if c in df.columns:
            weight_col = c
            break
    if ticker_col is None or weight_col is None:
        return pd.DataFrame(columns=["ticker", "weight (%)"])
    out = pd.DataFrame({
        "ticker": df[ticker_col].astype(str).str.upper().str.strip(),
        "weight (%)": pd.to_numeric(df[weight_col], errors="coerce"),
    })
    out = out.dropna(subset=["ticker", "weight (%)"])
    return out.reset_index(drop=True)

def _cache_path(etf: str) -> str:
    return os.path.join(CACHE_DIR, f"{etf}_holdings.csv")

def _save_cache(etf: str, df: pd.DataFrame) -> None:
    try:
        df.to_csv(_cache_path(etf), index=False)
    except Exception:
        pass  # cache I/O should never crash fetch

def _load_cache(etf: str) -> Optional[pd.DataFrame]:
    path = _cache_path(etf)
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            return _normalize_columns(df)
        except Exception:
            return None
    return None

def _try_csv(sess: requests.Session, etf: str) -> Optional[pd.DataFrame]:
    for url in CSV_CANDIDATES.get(etf, []):
        try:
            r = sess.get(url, timeout=20)
            ctype = (r.headers.get("Content-Type") or "").lower()
            if r.status_code == 200 and r.text and "html" not in ctype:
                df = pd.read_csv(StringIO(r.text))
                return _normalize_columns(df)
        except Exception:
            continue
    return None

def _raw_fetch() -> Dict[str, pd.DataFrame]:
    """
    Fetch latest ARK holdings per ETF with retry + cache fallback.
    Controlled via ARK_ETFS env (comma-separated), defaults to keys in CSV_CANDIDATES.
    """
    etfs_env = os.getenv("ARK_ETFS")
    etfs = [e.strip().upper() for e in (etfs_env.split(",") if etfs_env else CSV_CANDIDATES.keys())]
    sess = _session()

    out: Dict[str, pd.DataFrame] = {}
    for etf in etfs:
        df = _try_csv(sess, etf)
        if df is not None and not df.empty:
            _save_cache(etf, df)
            out[etf] = df
            continue

        # Fallback to cache
        cached = _load_cache(etf)
        if cached is not None and not cached.empty:
            if _once_per(etf, 60):
                print(f"[ARK] Using cached holdings for {etf} (live fetch unavailable).")
            out[etf] = cached
        else:
            if _once_per(etf, 60):
                print(f"[ARK] No holdings available for {etf} (fetch & cache both unavailable).")
    return out

def fetch_ark_holdings() -> Dict[str, pd.DataFrame]:
    """
    Public entrypoint used by ARKAgent.
    Returns a dict like {"ARKK": DataFrame[ticker, weight (%)], ... }.
    Safe: wraps I/O with retries and returns {} on failure.
    """
    data = safe_fetch(_raw_fetch)
    if not data:
        return {}
    # Final sanity: ensure required columns present
    fixed: Dict[str, pd.DataFrame] = {}
    for etf, df in data.items():
        norm = _normalize_columns(df)
        if "ticker" in norm.columns and "weight (%)" in norm.columns and not norm.empty:
            fixed[etf] = norm
    return fixed

if __name__ == "__main__":
    d = fetch_ark_holdings()
    for etf, df in d.items():
        cols = [c for c in ["company", "ticker", "shares", "weight (%)"] if c in df.columns]
        print(f"=== {etf} ({len(df)} rows) ===")
        print(df[cols].head() if cols else df.head())
