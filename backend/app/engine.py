import io
import json
from pathlib import Path

import pandas as pd

RULES_DIR = Path(__file__).parent.parent / "rules"
MAX_DISPLAY_ROWS = 500


def load_schema(schema_id: str) -> dict:
    """Read rules/<schema_id>.json and return it as a plain Python dict."""
    path = RULES_DIR / f"{schema_id}.json"
    if not path.exists() or path.name.startswith("_"):
        raise FileNotFoundError(f"Schema '{schema_id}' nicht gefunden.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(file_bytes: bytes, schema: dict) -> dict:
    """
    Validate an in-memory Excel file against a JSON codelist profile.

    The schema must contain a "fields" object where each key is a field name
    and each value may have an "allowed_codes" list.

    Comparison is .strip().lower() on both the cell value and each allowed code,
    which eliminates bugs caused by case differences or invisible whitespace.

    Returns a dict that matches the ValidationReport TypeScript interface.
    """
    # ── 1. Parse Excel entirely in-memory ────────────────────────────────────
    # dtype=str is mandatory: it prevents pandas from silently converting
    # "m" to NaN or "04109" to 4109.0.
    buf = io.BytesIO(file_bytes)
    try:
        df = pd.read_excel(buf, dtype=str, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"Excel-Datei konnte nicht gelesen werden: {exc}") from exc

    # Normalize column headers once: strip + lowercase for reliable matching
    df.columns = [str(c).strip().lower() for c in df.columns]
    headers = list(df.columns)
    total_rows = len(df)

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
    errors:   list[dict] = []
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
    error_count = len(errors)
    success_rate = round(
        max(0.0, (1 - error_count / max(total_rows, 1)) * 100),
        2,
    )

    return {
        "schema_id":     schema.get("schema_id", "unknown"),
        "schema_name":   schema.get("schema_name", ""),
        "total_rows":    total_rows,
        "error_count":   error_count,
        "warning_count": len(warnings),
        "success_rate":  success_rate,
        "headers":       headers,
        "rows":          rows,
        "errors":        errors,
        "warnings":      warnings,
        "field_meta":    field_meta,
    }
