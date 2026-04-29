from __future__ import annotations

import csv
import logging
import os
import platform
import select
import sys
import termios
import threading
import time
import tty
from datetime import datetime
from typing import Optional

import pandas as pd
from colorama import Fore, Style, init as colorama_init

from config import (
    ALERT_THRESHOLDS,
    CSV_LOG_PATH,
    DASHBOARD_TITLE,
    DEFAULT_SYMBOLS,
    ENABLE_CSV_LOG,
    REFRESH_INTERVAL,
    TABLE_WIDTH,
)
from nse_session import NSESession
from scraper import fetch_multiple

# ── Initialise colorama (auto-reset on Windows too) ───────────
colorama_init(autoreset=True)

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Platform helpers ──────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"


def clear_screen() -> None:
    os.system("cls" if IS_WINDOWS else "clear")


# ── Colour helpers ────────────────────────────────────────────

def _colour_value(value, positive_good: bool = True) -> str:
    """Wrap a numeric value in ANSI colour based on sign."""
    try:
        f = float(value)
    except (ValueError, TypeError):
        return str(value)
    if f > 0:
        colour = Fore.GREEN if positive_good else Fore.RED
    elif f < 0:
        colour = Fore.RED if positive_good else Fore.GREEN
    else:
        colour = Fore.YELLOW
    return f"{colour}{value}{Style.RESET_ALL}"


def _fmt(value, decimals: int = 2, width: int = 10) -> str:
    """Format a float to fixed decimals, or return the raw string."""
    try:
        formatted = f"{float(value):,.{decimals}f}"
    except (ValueError, TypeError):
        formatted = str(value)
    return formatted.rjust(width)


# ── Table renderer ────────────────────────────────────────────
_SEP = "─" * TABLE_WIDTH

def _render_header() -> str:
    now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    title_line = f"  {Fore.CYAN}{Style.BRIGHT}{DASHBOARD_TITLE}{Style.RESET_ALL}"
    time_line  = f"  {Fore.WHITE}Last updated: {now}{Style.RESET_ALL}"
    col_header = (
        f"  {'SYMBOL':<12}"
        f"{'PRICE':>12}"
        f"{'CHANGE':>11}"
        f"{'% CHG':>9}"
        f"{'HIGH':>10}"
        f"{'LOW':>10}"
    )
    return "\n".join([
        "",
        _SEP,
        title_line,
        time_line,
        _SEP,
        f"{Fore.WHITE}{Style.BRIGHT}{col_header}{Style.RESET_ALL}",
        _SEP,
    ])


def _render_row(row: pd.Series) -> str:
    symbol    = str(row["Symbol"]).ljust(12)
    
    # Check for error status
    status = str(row.get("Status", ""))
    if row.get("Last Price") == "—" and status and status != "—":
        return f"  {Fore.WHITE}{symbol}{Style.RESET_ALL}  {Fore.RED}ERROR: {status}{Style.RESET_ALL}"

    price_raw = _fmt(row["Last Price"], 2, 12)
    chg_raw   = _fmt(row["Change"],     2, 11)
    pct_raw   = _fmt(row["% Change"],   2,  8)
    high_raw  = _fmt(row["High"],       2, 10)
    low_raw   = _fmt(row["Low"],        2, 10)

    # Colour the change columns
    try:
        pct_val = float(row["% Change"])
        price_col = _colour_value(price_raw, positive_good=True) if pct_val >= 0 else f"{Fore.RED}{price_raw}{Style.RESET_ALL}"
    except (ValueError, TypeError):
        price_col = price_raw

    chg_col = _colour_value(chg_raw)
    pct_col = _colour_value(f"{pct_raw}%")

    # Alert check
    _check_alert(row["Symbol"], row["% Change"])

    return (
        f"  {Fore.WHITE}{symbol}{Style.RESET_ALL}"
        f"{price_col}"
        f"{chg_col}"
        f"{pct_col}"
        f"{Fore.WHITE}{high_raw}{Style.RESET_ALL}"
        f"{Fore.WHITE}{low_raw}{Style.RESET_ALL}"
    )


def _render_footer(symbols: list[str]) -> str:
    sym_list = "  Watching: " + ", ".join(
        f"{Fore.CYAN}{s}{Style.RESET_ALL}" for s in symbols
    )
    controls = (
        f"  {Fore.YELLOW}Commands:{Style.RESET_ALL} "
        f"[{Fore.GREEN}add <SYMBOL>{Style.RESET_ALL}]  "
        f"[{Fore.GREEN}remove <SYMBOL>{Style.RESET_ALL}]  "
        f"[{Fore.GREEN}set <SYMBOL>{Style.RESET_ALL}]  "
        f"[{Fore.RED}exit{Style.RESET_ALL}]"
    )
    return "\n".join(["", _SEP, sym_list, controls, _SEP, ""])


def render_dashboard(df: pd.DataFrame, symbols: list[str]) -> None:
    clear_screen()
    print(_render_header())
    for _, row in df.iterrows():
        print(_render_row(row))
    print(_render_footer(symbols))


# ── Alert system ──────────────────────────────────────────────

_alerted: dict[str, float] = {}   # symbol → last alerted pct


def _check_alert(symbol: str, pct_change) -> None:
    if not ALERT_THRESHOLDS:
        return
    threshold = ALERT_THRESHOLDS.get(str(symbol).upper())
    if threshold is None:
        return
    try:
        pct = float(pct_change)
    except (ValueError, TypeError):
        return
    if abs(pct) >= threshold:
        last = _alerted.get(symbol, 0.0)
        if abs(pct - last) >= 0.1:          # debounce
            _alerted[symbol] = pct
            colour = Fore.GREEN if pct > 0 else Fore.RED
            print(
                f"\n  {Fore.YELLOW}⚠ ALERT{Style.RESET_ALL}  "
                f"{symbol}: {colour}{pct:+.2f}%{Style.RESET_ALL} "
                f"(threshold ±{threshold}%)"
            )


# ── CSV logger ────────────────────────────────────────────────

def _log_csv(df: pd.DataFrame) -> None:
    if not ENABLE_CSV_LOG:
        return
    timestamp = datetime.now().isoformat()
    file_exists = os.path.isfile(CSV_LOG_PATH)
    try:
        with open(CSV_LOG_PATH, "a", newline="") as fh:
            writer = csv.writer(fh)
            if not file_exists:
                writer.writerow(["Timestamp"] + list(df.columns))
            for _, row in df.iterrows():
                writer.writerow([timestamp] + list(row))
    except OSError as exc:
        logger.warning("CSV log failed: %s", exc)


# ── Input handling (non-blocking) ─────────────────────────────

class InputHandler:
    """
    Reads user input in a background thread without blocking the
    main refresh loop.  Works on POSIX and Windows.
    """

    def __init__(self) -> None:
        self._queue: list[str] = []
        self._lock  = threading.Lock()
        self._stop  = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                line = input()
            except EOFError:
                break
            with self._lock:
                self._queue.append(line.strip())

    def poll(self) -> Optional[str]:
        with self._lock:
            return self._queue.pop(0) if self._queue else None

    def stop(self) -> None:
        self._stop.set()


# ── Command parser ────────────────────────────────────────────

def _parse_command(raw: str, symbols: list[str]) -> tuple[list[str], bool]:
    """
    Parse a user command and return (updated_symbols, should_exit).

    Commands
    ────────
    exit                    → quit the program
    add <SYM>               → add symbol to watchlist
    remove <SYM>            → remove symbol from watchlist
    set <SYM> [SYM …]       → replace entire watchlist
    <SYM>                   → shorthand: set single symbol
    """
    parts = raw.upper().split()
    if not parts:
        return symbols, False

    cmd = parts[0]

    if cmd == "EXIT":
        return symbols, True

    if cmd == "ADD" and len(parts) >= 2:
        new_syms = [s for s in parts[1:] if s not in symbols]
        return symbols + new_syms, False

    if cmd == "REMOVE" and len(parts) >= 2:
        to_remove = set(parts[1:])
        updated = [s for s in symbols if s not in to_remove]
        return updated if updated else symbols, False   # keep at least one

    if cmd == "SET" and len(parts) >= 2:
        return list(dict.fromkeys(parts[1:])), False    # deduplicate, preserve order

    # bare symbol shorthand
    if len(parts) == 1 and cmd.isalpha():
        return [cmd], False

    return symbols, False


# ── Welcome banner ────────────────────────────────────────────

def _print_welcome() -> None:
    clear_screen()
    print(f"""
{_SEP}
  {Fore.CYAN}{Style.BRIGHT}{DASHBOARD_TITLE}{Style.RESET_ALL}
  {Fore.WHITE}National Stock Exchange of India  ·  Live Mode{Style.RESET_ALL}
{_SEP}

  {Fore.YELLOW}Default watchlist:{Style.RESET_ALL} {', '.join(DEFAULT_SYMBOLS)}

  {Fore.WHITE}You can type commands at any time:{Style.RESET_ALL}
    {Fore.GREEN}add INFY{Style.RESET_ALL}           add a symbol
    {Fore.GREEN}remove TCS{Style.RESET_ALL}         remove a symbol
    {Fore.GREEN}set SBIN ONGC{Style.RESET_ALL}      replace whole watchlist
    {Fore.GREEN}RELIANCE{Style.RESET_ALL}           shorthand: watch one symbol
    {Fore.RED}exit{Style.RESET_ALL}               quit

  {Fore.WHITE}Press Enter after each command.{Style.RESET_ALL}
  {Fore.WHITE}Leave blank and press Enter to start with defaults.{Style.RESET_ALL}

{_SEP}
""")


# ── Main loop ─────────────────────────────────────────────────

def main() -> None:
    _print_welcome()

    # Initial symbol selection
    try:
        raw = input(f"  {Fore.CYAN}Symbols to watch (or Enter for defaults): {Style.RESET_ALL}").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nBye!")
        sys.exit(0)

    if raw:
        symbols, exit_now = _parse_command(raw, DEFAULT_SYMBOLS)
        if exit_now:
            sys.exit(0)
    else:
        symbols = list(DEFAULT_SYMBOLS)

    print(f"\n  {Fore.YELLOW}Initialising session…{Style.RESET_ALL}")

    input_handler = InputHandler()

    with NSESession() as session:
        try:
            while True:
                # ── Fetch data ────────────────────────────────
                df = fetch_multiple(symbols, session)

                # ── Render ────────────────────────────────────
                render_dashboard(df, symbols)

                # ── Optional CSV log ──────────────────────────
                _log_csv(df)

                # ── Wait, checking for input every 0.2s ───────
                deadline = time.monotonic() + REFRESH_INTERVAL
                while time.monotonic() < deadline:
                    cmd_raw = input_handler.poll()
                    if cmd_raw is not None:
                        symbols, exit_now = _parse_command(cmd_raw, symbols)
                        if exit_now:
                            raise SystemExit(0)
                        # Re-fetch immediately after symbol change
                        break
                    time.sleep(0.2)

        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            input_handler.stop()

    clear_screen()
    print(f"\n  {Fore.CYAN}NSE Dashboard exited. Goodbye!{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
# main.py
# ─────────────────────────────────────────────────────────────
# NSE Live Stock Dashboard — CLI entry point.
#
# Features
# ────────
#  • Live refresh every REFRESH_INTERVAL seconds
#  • Colour-coded price movements (green / red / yellow)
#  • Dynamic symbol switching without restarting
#  • Graceful Ctrl-C exit
#  • Optional CSV logging (config.ENABLE_CSV_LOG)
#  • Alert hooks (config.ALERT_THRESHOLDS)
# ─────────────────────────────────────────────────────────────