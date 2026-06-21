#!/usr/bin/env python3
"""
testfile_generator.py — Testdatei-Generator für den XÖV-Prüfbaustein.

Liest den JSON-Monolithen der Validierungsregeln und erzeugt in testfiles/:
  test_small.xlsx / test_small.csv  — 20 Zeilen, ca. 8 Fehlerzeilen
  test_large.xlsx / test_large.csv  — 5 000 Zeilen, exakt 200 Fehlerzeilen

Nutzung (aus backend/):
  python testfile_generator.py
  python testfile_generator.py --schema rules/xauslaender_compiled.json --seed 7
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import pandas as pd

# ── Standardkonfiguration ─────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).resolve().parent
DEFAULT_JSON = SCRIPT_DIR / "rules" / "xauslaender_compiled.json"
TESTFILES    = SCRIPT_DIR / "testfiles"

N_COLUMNS    = 10     # Anzahl Spalten aus dem Schema
N_SMALL      = 20     # Zeilen in der kleinen Datei
N_SMALL_ERRS = 8      # davon Fehlerzeilen (klein)
N_LARGE      = 5_000  # Zeilen in der großen Datei
N_LARGE_ERRS = 200    # davon Fehlerzeilen (groß) — exakt

# Werte, die garantiert nicht in einer Codeliste auftauchen
_BAD_POOL = [
    "ERROR_VAL", "UNGÜLTIG", "Frau", "XYZ_999",
    "??", "N/A", "FEHLER", "INVALID_CODE",
]


# ── Schema laden ──────────────────────────────────────────────────────────────

def load_columns(path: Path, n: int) -> list[tuple[str, list[str]]]:
    """
    Gibt bis zu n (Spaltenname, allowed_codes)-Paare zurück.
    Iteration erfolgt in Einfügereihenfolge des JSON-Dicts (Python 3.7+).
    Nur Felder mit nicht-leerem allowed_codes-Array werden berücksichtigt.
    """
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)

    fields = schema.get("fields", {})

    if isinstance(fields, list):
        # Legacy-Format: list[{name/target_column, allowed_codes, ...}]
        iter_items = (
            (r.get("target_column") or r.get("name", ""), r)
            for r in fields
            if isinstance(r, dict)
        )
    else:
        # Monolithisches Format: {name: {allowed_codes, ...}}
        iter_items = fields.items()

    result: list[tuple[str, list[str]]] = []
    for name, rule in iter_items:
        if not name:
            continue
        codes = [str(c) for c in (rule.get("allowed_codes") or rule.get("codelist") or [])]
        if codes:
            result.append((name, codes))
        if len(result) >= n:
            break

    if not result:
        sys.exit(
            f"Fehler: Keine Felder mit allowed_codes in '{path}' gefunden.\n"
            "Bitte prüfen Sie, ob die JSON-Datei das monolithische Format hat."
        )
    return result


# ── Wert-Generatoren ─────────────────────────────────────────────────────────

def _good(codes: list[str]) -> str:
    return random.choice(codes)


def _bad(codes: list[str]) -> str:
    """Liefert einen Wert, der sicher NICHT in der Codeliste steht."""
    lower_set = {c.lower() for c in codes}
    pool = _BAD_POOL.copy()
    random.shuffle(pool)
    for v in pool:
        if v.lower() not in lower_set:
            return v
    # Extremfall: alle Pool-Werte kollidieren → generischer Fallback
    return f"__INV_{random.randint(1000, 9999)}__"


# ── Zeilen-Builder ────────────────────────────────────────────────────────────

def _valid_row(cols: list[tuple[str, list[str]]]) -> dict[str, str]:
    return {name: _good(codes) for name, codes in cols}


def _error_row_small(cols: list[tuple[str, list[str]]]) -> dict[str, str]:
    """
    Für die kleine Datei: realistische Streuung pro Zelle.
    Mindestens eine Zelle ist garantiert fehlerhaft oder leer.

    Verteilung (zufällig per Zelle):
      40 % → gültiger Code
      35 % → ungültiger Code  (UNGÜLTIGER_CODELISTEN_WERT)
      25 % → leer             (LEERES_FELD_WARNUNG)
    """
    row: dict[str, str] = {}
    forced_idx = random.randrange(len(cols))   # Mindestens ein Fehler

    for i, (name, codes) in enumerate(cols):
        r = random.random()
        if i == forced_idx:
            row[name] = "" if random.random() < 0.40 else _bad(codes)
        elif r < 0.25:
            row[name] = ""            # leer → Warning
        elif r < 0.60:
            row[name] = _bad(codes)   # ungültig → Error
        else:
            row[name] = _good(codes)  # korrekt
    return row


def _error_row_large(cols: list[tuple[str, list[str]]]) -> dict[str, str]:
    """
    Für die große Datei: genau 1–3 Zellen pro Fehlerzeile sind schlecht;
    der Rest ist korrekt — macht die Fehler realistischer.

    Aufteilung der schlechten Zellen:
      30 % → leer  (Warning)
      70 % → ungültiger Code (Error)
    """
    row = _valid_row(cols)
    n_bad = random.randint(1, min(3, len(cols)))

    for idx in random.sample(range(len(cols)), n_bad):
        name, codes = cols[idx]
        row[name] = "" if random.random() < 0.30 else _bad(codes)

    return row


# ── DataFrame-Assembler ──────────────────────────────────────────────────────

def _make_small(cols: list[tuple[str, list[str]]]) -> pd.DataFrame:
    n_errs = min(N_SMALL_ERRS, N_SMALL)
    error_idx = set(random.sample(range(N_SMALL), n_errs))
    rows = [
        _error_row_small(cols) if i in error_idx else _valid_row(cols)
        for i in range(N_SMALL)
    ]
    col_names = [name for name, _ in cols]
    return pd.DataFrame(rows, columns=col_names)


def _make_large(cols: list[tuple[str, list[str]]]) -> pd.DataFrame:
    error_idx = set(random.sample(range(N_LARGE), N_LARGE_ERRS))
    rows = [
        _error_row_large(cols) if i in error_idx else _valid_row(cols)
        for i in range(N_LARGE)
    ]
    col_names = [name for name, _ in cols]
    return pd.DataFrame(rows, columns=col_names)


# ── Datei-Schreiber ───────────────────────────────────────────────────────────

def _write_excel(df: pd.DataFrame, path: Path) -> None:
    # Leere Strings → echte NaN-Zellen, damit pd.isna() im Engine greift
    # und LEERES_FELD_WARNUNG erzeugt wird.
    df.replace("", pd.NA).to_excel(path, index=False, engine="openpyxl")
    _log_file(path, len(df))


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    # UTF-8 BOM (utf-8-sig) damit Excel Umlaute sofort korrekt darstellt.
    # Semikolon als Trennzeichen gemäß deutschem Locale-Standard.
    df.to_csv(
        path,
        index=False,
        sep=";",
        encoding="utf-8-sig",
        lineterminator="\r\n",
        na_rep="",
    )
    _log_file(path, len(df))


def _log_file(path: Path, rows: int) -> None:
    try:
        size_kb = path.stat().st_size / 1024
        print(f"  [OK]  {path.name:<35}  {rows:>5} Zeilen  {size_kb:>7.1f} KB")
    except OSError:
        print(f"  [OK]  {path.name:<35}  {rows:>5} Zeilen")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="XÖV-Testdatei-Generator — erstellt XLSX und CSV für den Prüfbaustein",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--schema", type=Path, default=DEFAULT_JSON, metavar="PATH",
        help="Pfad zur JSON-Regeldatei",
    )
    ap.add_argument(
        "--seed", type=int, default=42,
        help="Zufalls-Seed (für reproduzierbare Ergebnisse)",
    )
    ap.add_argument(
        "--columns", type=int, default=N_COLUMNS, metavar="N",
        help="Anzahl der Spalten aus dem Schema",
    )
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    random.seed(args.seed)

    # ── Schema laden ──────────────────────────────────────────────────────
    if not args.schema.exists():
        sys.exit(f"Schema nicht gefunden: {args.schema}")

    print(f"\nSchema   : {args.schema.name}")
    cols = load_columns(args.schema, args.columns)

    print(f"Spalten ({len(cols)}):")
    for name, codes in cols:
        print(f"  - {name[:65]:<65}  {len(codes):>4} Codes")

    # ── Ausgabeverzeichnis anlegen ────────────────────────────────────────
    TESTFILES.mkdir(parents=True, exist_ok=True)
    print(f"\nAusgabe  : {TESTFILES}\n")

    # ── Kleine Dateien (20 Zeilen) ────────────────────────────────────────
    df_small = _make_small(cols)
    _write_excel(df_small, TESTFILES / "test_small.xlsx")
    _write_csv  (df_small, TESTFILES / "test_small.csv")

    # ── Große Dateien (5 000 Zeilen, exakt 200 Fehlerzeilen) ──────────────
    df_large = _make_large(cols)
    _write_excel(df_large, TESTFILES / "test_large.xlsx")
    _write_csv  (df_large, TESTFILES / "test_large.csv")

    # ── Zusammenfassung ───────────────────────────────────────────────────
    errs_small = sum(
        1 for i, row in df_small.iterrows()
        if any(
            v == "" or (v != "" and v not in codes)
            for (_, codes), v in zip(cols, row)
        )
    )
    sep = "-" * 60
    print(
        f"\n{sep}\n"
        f"  test_small  : {N_SMALL} Zeilen, {errs_small} Fehlerzeilen\n"
        f"  test_large  : {N_LARGE} Zeilen, {N_LARGE_ERRS} Fehlerzeilen (exakt)\n"
        f"  Schema      : {args.schema.name}\n"
        f"  Seed        : {args.seed}\n"
        f"{sep}\n"
    )


if __name__ == "__main__":
    main()
