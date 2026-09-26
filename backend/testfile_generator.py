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

# ── XMeld-Konfiguration ───────────────────────────────────────────────────────

XMELD_JSON    = SCRIPT_DIR / "rules" / "xmeld_compiled.json"
TEST_DATA_DIR = SCRIPT_DIR / "test_data"

N_XMELD_COLS  = 10    # Anzahl XMeld-Spalten (bevorzugt kleine Codelisten)
N_XMELD_SMALL = 20    # Zeilen in den kleinen XMeld-Dateien
N_XMELD_BIG   = 5_000 # Zeilen in den großen XMeld-Dateien
ERROR_RATIO   = 0.20  # 20 % Fehlerzeilen

_XMELD_BAD_POOL = [
    "UNGUELTIG", "ошибка", "ERROR", "N/A",
    "FALSCH_CODE", "???", "INVALID_XMELD", "XX_FEHLER",
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


# ── XMeld-Generator ──────────────────────────────────────────────────────────

def _select_xmeld_cols(path: Path, n: int) -> list[tuple[str, list[str]]]:
    """
    Wählt bis zu n Spalten aus xmeld_compiled.json.

    Bevorzugt Felder mit kleinen Codelisten (2–50 Einträge), weil
    Test-Dateien mit menschenlesbaren Codes aussagekräftiger sind.
    Falls weniger als n solcher Felder existieren, werden weitere Felder
    mit allowed_codes (beliebiger Größe) ergänzt.
    """
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)

    fields = schema.get("fields", {})
    if not isinstance(fields, dict):
        sys.exit(f"Fehler: 'fields' in '{path}' ist kein Objekt.")

    preferred: list[tuple[str, list[str]]] = []
    fallback:  list[tuple[str, list[str]]] = []

    for field_name, rule in fields.items():
        codes = [str(c) for c in (rule.get("allowed_codes") or [])]
        if not codes:
            continue
        if 2 <= len(codes) <= 50:
            preferred.append((field_name, codes))
        else:
            fallback.append((field_name, codes))

    combined = preferred + fallback
    if not combined:
        sys.exit(
            f"Fehler: Keine Felder mit allowed_codes in '{path}' gefunden.\n"
            "Bitte prüfen Sie, ob xmeld_compiled.json korrekt kompiliert wurde."
        )
    return combined[:n]


def _bad_xmeld(codes: list[str]) -> str:
    """Ungültiger Wert, der garantiert nicht in der XMeld-Codeliste steht."""
    lower_set = {c.lower() for c in codes}
    pool = _XMELD_BAD_POOL.copy()
    random.shuffle(pool)
    for v in pool:
        if v.lower() not in lower_set:
            return v
    return f"__XMELD_INV_{random.randint(1000, 9999)}__"


def _error_row_xmeld(cols: list[tuple[str, list[str]]]) -> dict[str, str]:
    """
    Fehlerzeile für XMeld: 1–2 Zellen sind absichtlich fehlerhaft.

    Fehlertypen (zufällig pro fehlerhafter Zelle):
      40 % → leer  (simuliert fehlendes Pflichtfeld → LEERES_FELD_WARNUNG)
      60 % → ungültiger Code               (→ UNGÜLTIGER_CODELISTEN_WERT)

    Alle übrigen Zellen enthalten gültige Codes.
    """
    row = {name: _good(codes) for name, codes in cols}
    n_bad = random.randint(1, min(2, len(cols)))
    for idx in random.sample(range(len(cols)), n_bad):
        name, codes = cols[idx]
        row[name] = "" if random.random() < 0.40 else _bad_xmeld(codes)
    return row


def _make_df_ratio(
    cols: list[tuple[str, list[str]]],
    n_rows: int,
    error_ratio: float,
) -> pd.DataFrame:
    """DataFrame mit exakt round(n_rows * error_ratio) Fehlerzeilen."""
    n_errs   = round(n_rows * error_ratio)
    err_idx  = set(random.sample(range(n_rows), min(n_errs, n_rows)))
    col_names = [name for name, _ in cols]
    rows = [
        _error_row_xmeld(cols) if i in err_idx else _valid_row(cols)
        for i in range(n_rows)
    ]
    return pd.DataFrame(rows, columns=col_names)


def generate_xmeld_files(
    schema_path: Path,
    out_dir: Path,
    n_cols: int,
    seed: int,
) -> None:
    """Generiert 4 XMeld-Testdateien (2 × XLSX + 2 × CSV) in out_dir."""
    if not schema_path.exists():
        sys.exit(f"XMeld-Schema nicht gefunden: {schema_path}")

    random.seed(seed)
    cols = _select_xmeld_cols(schema_path, n_cols)

    print(f"\nXMeld-Schema : {schema_path.name}")
    print(f"Spalten ({len(cols)}):")
    for name, codes in cols:
        print(f"  - {name[:65]:<65}  {len(codes):>4} Codes")

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nAusgabe : {out_dir}\n")

    n_small_errs = round(N_XMELD_SMALL * ERROR_RATIO)
    n_big_errs   = round(N_XMELD_BIG   * ERROR_RATIO)

    df_small = _make_df_ratio(cols, N_XMELD_SMALL, ERROR_RATIO)
    df_big   = _make_df_ratio(cols, N_XMELD_BIG,   ERROR_RATIO)

    _write_excel(df_small, out_dir / "xmeld_small_test.xlsx")
    _write_excel(df_big,   out_dir / "xmeld_big_test.xlsx")
    _write_csv  (df_small, out_dir / "xmeld_small_test.csv")
    _write_csv  (df_big,   out_dir / "xmeld_big_test.csv")

    sep = "-" * 60
    print(
        f"\n{sep}\n"
        f"  xmeld_small_test : {N_XMELD_SMALL} Zeilen, ~{n_small_errs} Fehlerzeilen ({ERROR_RATIO:.0%})\n"
        f"  xmeld_big_test   : {N_XMELD_BIG} Zeilen, ~{n_big_errs} Fehlerzeilen ({ERROR_RATIO:.0%})\n"
        f"  Schema           : {schema_path.name}\n"
        f"  Seed             : {seed}\n"
        f"{sep}\n"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="XÖV-Testdatei-Generator — erstellt XLSX und CSV für XAusländer und XMeld",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--schema", type=Path, default=DEFAULT_JSON, metavar="PATH",
        help="Pfad zur XAusländer JSON-Regeldatei",
    )
    ap.add_argument(
        "--xmeld-schema", type=Path, default=XMELD_JSON, metavar="PATH",
        help="Pfad zur XMeld JSON-Regeldatei",
    )
    ap.add_argument(
        "--seed", type=int, default=42,
        help="Zufalls-Seed (für reproduzierbare Ergebnisse)",
    )
    ap.add_argument(
        "--columns", type=int, default=N_COLUMNS, metavar="N",
        help="Anzahl der Spalten aus dem XAusländer-Schema",
    )
    ap.add_argument(
        "--xmeld-columns", type=int, default=N_XMELD_COLS, metavar="N",
        help="Anzahl der Spalten aus dem XMeld-Schema",
    )
    ap.add_argument(
        "--no-xauslaender", action="store_true",
        help="XAusländer-Dateien überspringen",
    )
    ap.add_argument(
        "--no-xmeld", action="store_true",
        help="XMeld-Dateien überspringen",
    )
    return ap.parse_args()


def main() -> None:
    args = _parse_args()

    # ── XAusländer-Dateien ────────────────────────────────────────────────
    if not args.no_xauslaender:
        random.seed(args.seed)

        if not args.schema.exists():
            sys.exit(f"Schema nicht gefunden: {args.schema}")

        print(f"\nSchema   : {args.schema.name}")
        cols = load_columns(args.schema, args.columns)

        print(f"Spalten ({len(cols)}):")
        for name, codes in cols:
            print(f"  - {name[:65]:<65}  {len(codes):>4} Codes")

        TESTFILES.mkdir(parents=True, exist_ok=True)
        print(f"\nAusgabe  : {TESTFILES}\n")

        df_small = _make_small(cols)
        _write_excel(df_small, TESTFILES / "test_small.xlsx")
        _write_csv  (df_small, TESTFILES / "test_small.csv")

        df_large = _make_large(cols)
        _write_excel(df_large, TESTFILES / "test_large.xlsx")
        _write_csv  (df_large, TESTFILES / "test_large.csv")

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

    # ── XMeld-Dateien ─────────────────────────────────────────────────────
    if not args.no_xmeld:
        generate_xmeld_files(
            schema_path = args.xmeld_schema,
            out_dir     = TEST_DATA_DIR,
            n_cols      = args.xmeld_columns,
            seed        = args.seed,
        )


if __name__ == "__main__":
    main()
