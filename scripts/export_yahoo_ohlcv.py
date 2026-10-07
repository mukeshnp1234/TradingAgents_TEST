"""Download the longest daily Yahoo Finance OHLCV history and write Excel.

Yahoo's history-page CSV download is a paid feature. This script uses the
same yfinance chart client as the rest of TradingAgents and asks for
``period="max"``, which is every daily bar Yahoo stores (listing date
through the latest session). Intraday intervals are much shorter, so this
export stays on daily bars.

NSE symbols need the exchange suffix, for example ``HDFCBANK.NS``.

    python scripts/export_yahoo_ohlcv.py HDFCBANK.NS
    python scripts/export_yahoo_ohlcv.py HDFCBANK.NS RELIANCE.NS TCS.NS -o exports/nse_ohlcv.xlsx
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow `python scripts/export_yahoo_ohlcv.py` without an editable install.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.stockstats_utils import yf_retry

OHLCV_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close"]
_INVALID_SHEET_CHARS = re.compile(r"[:\\/?*\[\]]")


def shape_history(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn a yfinance history frame into Date, OHLC, Adj Close, and Volume.

    Dates are timezone-naive so Excel stores a plain date. Prices stay
    unadjusted when the caller requested ``auto_adjust=False``; Adj Close
    is filled from Close only if Yahoo omitted it.
    """
    if raw is None or raw.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.reset_index()

    date_col = "Date" if "Date" in frame.columns else frame.columns[0]
    if date_col != "Date":
        frame = frame.rename(columns={date_col: "Date"})

    dates = pd.to_datetime(frame["Date"], errors="coerce")
    # Drop the timezone but keep the exchange calendar day (IST midnight
    # must stay on that date, not shift to the previous UTC day).
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    frame["Date"] = dates.dt.normalize()

    if "Adj Close" not in frame.columns and "Close" in frame.columns:
        frame["Adj Close"] = frame["Close"]

    missing = [column for column in OHLCV_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Yahoo history is missing columns: {', '.join(missing)}")

    frame = frame.loc[:, OHLCV_COLUMNS].dropna(subset=["Date"]).sort_values("Date")
    for column in PRICE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").round(2)
    frame["Volume"] = pd.to_numeric(frame["Volume"], errors="coerce").round(0).astype("Int64")
    return frame.reset_index(drop=True)


def sheet_name(symbol: str) -> str:
    """Excel sheet titles are at most 31 characters and reject some punctuation."""
    cleaned = _INVALID_SHEET_CHARS.sub("-", symbol.strip()) or "Sheet"
    return cleaned[:31]


def default_output_path(symbols: list[str]) -> Path:
    if len(symbols) == 1:
        return Path("exports") / f"{symbols[0]}_ohlcv.xlsx"
    return Path("exports") / "ohlcv.xlsx"


def fetch_max_daily(symbol: str) -> pd.DataFrame:
    """Download every daily bar Yahoo has for ``symbol``."""
    ticker = yf.Ticker(symbol)
    raw = yf_retry(
        lambda: ticker.history(
            period="max",
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
    )
    return shape_history(raw)


def write_workbook(frames: dict[str, pd.DataFrame], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        used: set[str] = set()
        for symbol, frame in frames.items():
            name = sheet_name(symbol)
            if name in used:
                suffix = 2
                while f"{name[:28]}_{suffix}" in used:
                    suffix += 1
                name = f"{name[:28]}_{suffix}"
            used.add(name)
            frame.to_excel(writer, sheet_name=name, index=False)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the maximum daily Yahoo Finance OHLCV history to Excel."
    )
    parser.add_argument(
        "symbols",
        nargs="*",
        default=["HDFCBANK.NS"],
        help="Ticker symbols. NSE names need the .NS suffix. Default: HDFCBANK.NS",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Workbook path. Default: exports/<SYMBOL>_ohlcv.xlsx, or exports/ohlcv.xlsx for several symbols.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    symbols = [symbol.strip().upper() for symbol in args.symbols if symbol.strip()]
    if not symbols:
        print("No ticker symbols given.", file=sys.stderr)
        return 1

    output = args.output or default_output_path(symbols)
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        frame = fetch_max_daily(symbol)
        if frame.empty:
            print(f"No daily history found for {symbol}.", file=sys.stderr)
            return 1
        first = frame["Date"].iloc[0].strftime("%Y-%m-%d")
        last = frame["Date"].iloc[-1].strftime("%Y-%m-%d")
        print(f"{symbol}: {len(frame)} daily rows from {first} to {last}")
        frames[symbol] = frame

    write_workbook(frames, output)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
