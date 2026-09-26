import csv as _csv
import io
import json
from pathlib import Path

import pandas as pd

RULES_DIR = Path(__file__).parent.parent / "rules"
MAX_DISPLAY_ROWS = 500


def _read_dataframe(file_bytes: bytes, nrows: int | None = None) -> pd.DataFrame:
    """
    Auto-detect file format from magic bytes and return a DataFrame.

    Supports:
      - XLSX / XLSM (ZIP-based, magic PK\\x03\\x04)
      - CSV  with auto-detected encoding (UTF-8 BOM, UTF-16, UTF-8, Latin-1)
            and auto-detected separator (, ; \\t |)

    Raises ValueError with a user-readable German message on any parse error.
    """
    magic = file_bytes[:4]

    # ── Excel (XLSX/XLSM) ────────────────────────────────────────────────────
    if magic[:2] == b"PK":
        buf = io.BytesIO(file_bytes)
        return pd.read_excel(buf, dtype=str, engine="openpyxl", nrows=nrows)

    # ── Old XLS (OLE2 Compound Document) — needs xlrd, not installed ─────────
    if magic == b"\xd0\xcf\x11\xe0":
        raise ValueError(
            "XLS-Dateien (altes Excel 97–2003 Format) werden nicht unterstützt. "
            "Bitte speichern Sie die Datei als .xlsx oder .csv."
        )

    # ── CSV (treat everything else as text) ──────────────────────────────────
    # 1. Detect encoding via BOM; fall back to UTF-8 → Latin-1
    if file_bytes[:3] == b"\xef\xbb\xbf":
        encoding = "utf-8-sig"
    elif file_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
        encoding = "utf-16"
    else:
        try:
            file_bytes.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoding = "latin-1"

    # 2. Sniff separator from first 8 KB
    sample = file_bytes[:8192].decode(encoding, errors="replace")
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=",;\t|")
        sep = dialect.delimiter
    except _csv.Error:
        # German government files typically use semicolons
        sep = ";" if sample.count(";") >= sample.count(",") else ","

    buf = io.BytesIO(file_bytes)
    return pd.read_csv(buf, dtype=str, encoding=encoding, sep=sep, nrows=nrows)


def load_schema(schema_id: str) -> dict:
    """Read rules/<schema_id>.json and return it as a plain Python dict."""
    path = RULES_DIR / f"{schema_id}.json"
    if not path.exists() or path.name.startswith("_"):
        raise FileNotFoundError(f"Schema '{schema_id}' nicht gefunden.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_headers(headers: list[str], schema: dict) -> list[dict]:
    """
    Pre-validates file column headers against the schema.

    Three-tier check:
      1. Column in `fields`      → codelist validation will run  → no notice
      2. Column in `known_fields` → legitimate XÖV field, no codelist → no notice
      3. Column in neither        → amber NICHT_IM_PROFIL notice

    `known_fields` is a flat list of ALL xs:element names from the XSD (lowercase),
    added to the monolith by add_known_fields.py.  It covers date fields, string
    fields, etc. that are part of the standard but have no Genericode codelist.
    """
    field_defs = schema.get("fields", {})

    if isinstance(field_defs, dict):
        codelist_keys: set[str] = {k.strip().lower() for k in field_defs}
    elif isinstance(field_defs, list):
        codelist_keys = {
            (r.get("name") or r.get("target_column") or "").strip().lower()
            for r in field_defs
            if isinstance(r, dict)
        }
    else:
        codelist_keys = set()

    # known_fields: every xs:element name from the XSD (no codelist required)
    known_fields: set[str] = {
        str(k).strip().lower()
        for k in schema.get("known_fields", [])
    }

    # Union: anything known to the schema — either validated or just recognised
    all_known = codelist_keys | known_fields

    schema_name = schema.get("schema_name") or schema.get("schema_id") or "Protokoll"
    errors: list[dict] = []

    for col in headers:
        if col not in all_known:
            errors.append({
                "row_index":      0,
                "column_name":    col,
                "invalid_value":  col,
                "error_type":     "NICHT_IM_PROFIL",
                "fix_suggestion": (
                    f'Hinweis: Spalte "{col}" ist im Validierungsprofil '
                    f'"{schema_name}" nicht enthalten und wird nicht geprüft.'
                ),
            })

    return errors


def read_headers(file_bytes: bytes) -> list[str]:
    """
    Read only the header row (column names) from an Excel or CSV file.
    Used by the /preview endpoint to populate the mapping UI without
    running full validation.
    """
    try:
        df = _read_dataframe(file_bytes, nrows=0)
    except Exception as exc:
        raise ValueError(f"Datei-Kopfzeile konnte nicht gelesen werden: {exc}") from exc
    return [str(c).strip().lower() for c in df.columns]


def validate(
    file_bytes: bytes,
    schema: dict,
    mapping: dict[str, str | None] | None = None,
) -> dict:
    """
    Validate an in-memory Excel file against a JSON codelist profile.

    mapping (optional): {normalized_file_col → schema_key | None}
      Built by the frontend mapping UI.  When present:
        - Columns with a non-null target_key are renamed to that key before
          validation, so the engine finds them in codelist_lookup.
        - Columns mapped to None are dropped (user chose "Überspringen").
        - Columns absent from the mapping dict are left as-is (may produce
          NICHT_IM_PROFIL header notices if they are not in the schema).

    Phase 0 (pre-validation): validate_headers() flags every column not in
    the schema as NICHT_IM_PROFIL (row_index=0, counted as warning).

    Phase 1+: codelist validation on each cell of schema-known columns.

    Returns a dict that matches the ValidationReport TypeScript interface.
    """
    # ── 1. Parse file entirely in-memory (Excel or CSV) ─────────────────────
    try:
        df = _read_dataframe(file_bytes)
    except Exception as exc:
        raise ValueError(f"Datei konnte nicht gelesen werden: {exc}") from exc

    # Normalize column headers once: strip + lowercase for reliable matching
    df.columns = [str(c).strip().lower() for c in df.columns]

    # ── 1b. Apply user mapping (if provided) ─────────────────────────────────
    if mapping:
        rename: dict[str, str] = {}
        drop:   list[str]      = []
        for file_col, target_key in mapping.items():
            fc = str(file_col).strip().lower()
            if fc not in df.columns:
                continue
            if target_key:
                rename[fc] = str(target_key).strip().lower()
            else:
                drop.append(fc)
        if rename:
            df = df.rename(columns=rename)
        if drop:
            df = df.drop(columns=drop, errors="ignore")

    headers = list(df.columns)
    total_rows = len(df)

    # ── Phase 0: Pre-validate headers ─────────────────────────────────────────
    # Unknown columns → row_index=0 notice + amber <th> in UI.
    # Validation continues; those columns are silently skipped per-cell.
    header_errors = validate_headers(headers, schema)

    # ── 2. Build codelist lookup from the JSON profile ────────────────────────
    # Pre-normalize allowed codes once here, not per row, for performance.
    # Structure: { lowercase_field_name -> { "original": [...], "lower": [...] } }
    #
    # "fields" can be either:
    #   dict  → monolithic compiled format: {"field_name": {"allowed_codes": [...]}}
    #   list  → legacy format:              [{"name": "field_name", "codelist": [...]}]
    field_defs = schema.get("fields", {})
    codelist_lookup: dict[str, dict] = {}

    if isinstance(field_defs, dict):
        # Monolithic compiled format
        for field_name, rule in field_defs.items():
            allowed_codes = rule.get("allowed_codes") or rule.get("codelist")
            if not allowed_codes:
                continue
            key = str(field_name).strip().lower()
            codelist_lookup[key] = {
                "original": [str(c) for c in allowed_codes],
                "lower":    [str(c).strip().lower() for c in allowed_codes],
            }
    elif isinstance(field_defs, list):
        # Legacy list format
        for rule in field_defs:
            if not isinstance(rule, dict):
                continue
            field_name = rule.get("name") or rule.get("target_column") or ""
            if not field_name:
                continue
            allowed_codes = rule.get("allowed_codes") or rule.get("codelist")
            if not allowed_codes:
                continue
            key = str(field_name).strip().lower()
            codelist_lookup[key] = {
                "original": [str(c) for c in allowed_codes],
                "lower":    [str(c).strip().lower() for c in allowed_codes],
            }

    # ── 3. Collect field display-name metadata for frontend tooltips ─────────
    # Extracted once at schema load time; keys are the same lowercased names
    # as in headers so the frontend can do a direct O(1) lookup per column.
    field_meta: dict[str, dict] = {}
    if isinstance(field_defs, dict):
        for field_name, rule in field_defs.items():
            key = str(field_name).strip().lower()
            field_meta[key] = {
                "display_name_short": rule.get("display_name_short") or "",
                "display_name_long":  rule.get("display_name_long")  or "",
            }
    elif isinstance(field_defs, list):
        for rule in field_defs:
            if not isinstance(rule, dict):
                continue
            field_name = rule.get("name") or rule.get("target_column") or ""
            if not field_name:
                continue
            key = str(field_name).strip().lower()
            field_meta[key] = {
                "display_name_short": rule.get("display_name_short") or "",
                "display_name_long":  rule.get("display_name_long")  or "",
            }

    # ── 4. Validate row by row ────────────────────────────────────────────────
    errors:   list[dict] = list(header_errors)   # row_index=0 entries first
    warnings: list[dict] = []

    for idx, row in df.iterrows():
        # row_index must equal arrayIdx + 1 from the frontend's rows[] array.
        # pandas default RangeIndex: idx=0 → first data row → row_index=1.
        row_index = int(idx) + 1

        for col in headers:
            entry = codelist_lookup.get(col)
            if entry is None:
                continue  # no rule for this column → skip

            raw = row[col]
            if pd.isna(raw) or not str(raw).strip():
                warnings.append({
                    "row_index":      row_index,
                    "column_name":    col,
                    "invalid_value":  "",
                    "error_type":     "LEERES_FELD_WARNUNG",
                    "fix_suggestion": "Hinweis: Dieses Feld ist leer. Bitte prüfen Sie, ob das für diesen Datensatz korrekt ist.",
                })
                continue

            cell_value = str(raw).strip().lower()

            if cell_value not in entry["lower"]:
                # Build a readable hint using the original (non-lowercased) codes
                original = entry["original"]
                hint_codes = ", ".join(original[:10])
                hint = f"Erlaubte Werte: {hint_codes}" + ("…" if len(original) > 10 else "")

                errors.append({
                    "row_index":     row_index,
                    "column_name":   col,
                    "invalid_value": str(raw).strip(),
                    "error_type":    "UNGÜLTIGER_CODELISTEN_WERT",
                    "fix_suggestion": hint,
                })

    # ── 4. Build display grid (first 500 rows, all values as strings) ─────────
    display_df = df.head(MAX_DISPLAY_ROWS).fillna("")
    rows = [
        {col: str(display_df.at[i, col]) for col in headers}
        for i in display_df.index
    ]

    # ── 5. Compute summary statistics ─────────────────────────────────────────
    # Header notices (row_index=0) are informational — they live in errors[] so
    # the frontend can highlight <th> cells, but they must not distort the
    # row-level error rate.  Only row_index>0 entries count as true errors.
    row_error_count = sum(1 for e in errors if e["row_index"] > 0)
    success_rate = round(
        max(0.0, (1 - row_error_count / max(total_rows, 1)) * 100),
        2,
    )

    return {
        "schema_id":     schema.get("schema_id", "unknown"),
        "schema_name":   schema.get("schema_name", ""),
        "total_rows":    total_rows,
        "error_count":   row_error_count,
        "warning_count": len(warnings) + len(header_errors),
        "success_rate":  success_rate,
        "headers":       headers,
        "rows":          rows,
        "errors":        errors,
        "warnings":      warnings,
        "field_meta":    field_meta,
    }
