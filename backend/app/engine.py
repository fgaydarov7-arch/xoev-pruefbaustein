from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Optional

import pandas as pd

from .schemas import FieldRule, SchemaConfig, ValidationError, ValidationReport


# ---------------------------------------------------------------------------
# Checksum validators
# ---------------------------------------------------------------------------

def _validate_steuer_id(value: str) -> bool:
    """BZSt Prüfziffernberechnung für die 11-stellige Steuer-Identifikationsnummer."""
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        return False
    # First digit must not be 0
    if digits[0] == "0":
        return False
    # First three digits must not contain any digit more than 3 times
    first_three = digits[:3]
    for ch in set(first_three):
        if first_three.count(ch) > 3:
            return False
    # Official modulo-11 algorithm (BZSt)
    product = 10
    for i in range(10):
        total = (int(digits[i]) + product) % 10
        if total == 0:
            total = 10
        product = (total * 2) % 11
    check = 11 - product
    if check == 10:
        check = 0
    return check == int(digits[10])


def _validate_iban(value: str) -> bool:
    """ISO 13616 IBAN-Validierung via Modulo-97-Algorithmus."""
    iban = re.sub(r"\s", "", value).upper()
    if len(iban) < 5:
        return False
    # Rearrange: move first 4 chars to the end
    rearranged = iban[4:] + iban[:4]
    # Replace letters with digits (A=10, B=11, …, Z=35)
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        elif ch.isalpha():
            numeric += str(ord(ch) - ord("A") + 10)
        else:
            return False
    return int(numeric) % 97 == 1


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_DATE_FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"]


def _parse_date(value: str) -> Optional[datetime]:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Pandas float fix for codes / PLZ
# ---------------------------------------------------------------------------

def _coerce_cell_to_str(value: object) -> str:
    """Convert a pandas cell to string, safely handling floats that represent integer codes."""
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        # e.g. 4109.0 → "04109" is NOT recoverable here without knowing expected width,
        # so we strip the trailing .0 and return the integer string.
        int_val = int(value)
        # Preserve the raw integer representation; leading zeros already lost by pandas float parsing.
        return str(int_val)
    return str(value).strip()


def _fix_plz_float(series: pd.Series) -> pd.Series:
    """Re-pad PLZ values that pandas silently converted to float (e.g. 4109.0 → '04109')."""
    result = []
    for v in series:
        s = _coerce_cell_to_str(v)
        # If it looks like a 4-digit number that should be a PLZ, re-pad to 5 digits
        if re.fullmatch(r"[0-9]{4}", s):
            s = s.zfill(5)
        result.append(s)
    return pd.Series(result, index=series.index)


def _fix_gemeindeschluessel_float(series: pd.Series) -> pd.Series:
    """Re-pad Gemeindeschlüssel values that pandas read as float (8 digits expected)."""
    result = []
    for v in series:
        s = _coerce_cell_to_str(v)
        if re.fullmatch(r"[0-9]{5,7}", s):
            s = s.zfill(8)
        result.append(s)
    return pd.Series(result, index=series.index)


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------

class XovValidator:
    """Stateless, in-memory XÖV validation engine driven by JSON rule files."""

    def __init__(self, schema: SchemaConfig) -> None:
        self._schema = schema
        # Build a case-insensitive lookup: canonical_name → FieldRule
        self._field_map: dict[str, FieldRule] = {
            f.name.lower(): f for f in schema.fields
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def validate(self, file_bytes: bytes, filename: str) -> ValidationReport:
        df = self._load_dataframe(file_bytes, filename)
        df = self._normalize_headers(df)
        df = self._apply_float_fixes(df)

        errors: list[ValidationError] = []
        total_rows = len(df)

        # --- 1. ПРОВЕРЯЕМ ТОЛЬКО ТЕ КОЛОНКИ, КОТОРЫЕ РЕАЛЬНО ЕСТЬ В EXCEL ---
        for col_lower in df.columns:
            # Ищем правило в нашей карте по маленьким буквам
            field_rule = self._field_map.get(col_lower)
            
            # Если для этой колонки вообще есть правила в JSON
            if field_rule:
                series = df[col_lower]
                for idx, raw in enumerate(series, start=1):
                    cell = _coerce_cell_to_str(raw)
                    error = self._validate_cell(cell, field_rule, idx)
                    if error:
                        errors.append(error)

        # --- 2. (ОПЦИОНАЛЬНО) КРИТИЧЕСКИЕ ПФЛИХТФЕЛЬДЕРЫ ---
        # Если тебе ВСЁ-ТАКИ нужно, чтобы какая-то колонка была ВСЕГДА (например, ID или Фамилия),
        # жестко пропиши её имя сюда. Все остальные 1000 полей движок будет игнорировать, если их нет.
        hard_required_fields = ["geschlecht", "staatsangehoerigkeit"] # Добавь сюда ключевые поля, если надо
        
        for req_field in hard_required_fields:
            if req_field not in df.columns:
                # Ищем оригинальное (красивое) имя поля из карты
                orig_rule = self._field_map.get(req_field)
                orig_name = orig_rule.name if orig_rule else req_field
                
                errors.append(ValidationError(
                    row_index=0,
                    column_name=orig_name,
                    invalid_value="(Spalte fehlt)",
                    error_type="FEHLENDE_PFLICHTSPALTE",
                    fix_suggestion=f"Die kritische Pflichtspalte '{orig_name}' fehlt in der Datei.",
                ))

        error_count = len(errors)
        success_rate = round((1 - error_count / max(total_rows, 1)) * 100, 2)
        return ValidationReport(
            schema_id=self._schema.schema_id,
            schema_name=self._schema.schema_name,
            total_rows=total_rows,
            error_count=error_count,
            success_rate=max(0.0, success_rate),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_dataframe(self, file_bytes: bytes, filename: str) -> pd.DataFrame:
        buf = io.BytesIO(file_bytes)
        lower_name = filename.lower()
        if lower_name.endswith(".xlsx") or lower_name.endswith(".xls"):
            df = pd.read_excel(buf, dtype=str, engine="openpyxl")
        else:
            # Try UTF-8 first, fall back to latin-1 (common in German municipal exports)
            try:
                df = pd.read_csv(buf, dtype=str, encoding="utf-8-sig", sep=None, engine="python")
            except UnicodeDecodeError:
                buf.seek(0)
                df = pd.read_csv(buf, dtype=str, encoding="latin-1", sep=None, engine="python")
        return df

    def _normalize_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Lowercase all column names for case-insensitive matching."""
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df

    def _apply_float_fixes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Re-pad columns that are expected to be zero-padded codes."""
        plz_fields = [
            f.name.lower() for f in self._schema.fields
            if f.type == "plz" or (f.regex and f.regex == r"^[0-9]{5}$")
        ]
        gs_fields = [
            f.name.lower() for f in self._schema.fields
            if f.regex and f.regex == r"^[0-9]{8}$"
        ]
        for col in plz_fields:
            if col in df.columns:
                df[col] = _fix_plz_float(df[col])
        for col in gs_fields:
            if col in df.columns:
                df[col] = _fix_gemeindeschluessel_float(df[col])
        return df

    def _validate_cell(
        self, cell: str, rule: FieldRule, row_index: int
    ) -> Optional[ValidationError]:
        # Required check
        if not cell:
            if rule.required:
                return ValidationError(
                    row_index=row_index,
                    column_name=rule.name,
                    invalid_value="(leer)",
                    error_type="PFLICHTFELD_LEER",
                    fix_suggestion=rule.fix_suggestion or f"Das Pflichtfeld '{rule.name}' darf nicht leer sein.",
                )
            return None

        # Type-specific validation
        if rule.type == "steuer_id":
            if not _validate_steuer_id(cell):
                return ValidationError(
                    row_index=row_index,
                    column_name=rule.name,
                    invalid_value=cell,
                    error_type="UNGUELTIGE_STEUER_ID",
                    fix_suggestion=rule.fix_suggestion or "Steuer-ID muss 11-stellig sein und der BZSt-Prüfziffer entsprechen.",
                )

        elif rule.type == "iban":
            if not _validate_iban(cell):
                return ValidationError(
                    row_index=row_index,
                    column_name=rule.name,
                    invalid_value=cell,
                    error_type="UNGUELTIGE_IBAN",
                    fix_suggestion=rule.fix_suggestion or "Bitte eine gültige IBAN gemäß ISO 13616 angeben.",
                )

        elif rule.type == "date":
            if _parse_date(cell) is None:
                return ValidationError(
                    row_index=row_index,
                    column_name=rule.name,
                    invalid_value=cell,
                    error_type="UNGÜLTIGES_DATUM",
                    fix_suggestion=rule.fix_suggestion or "Format: TT.MM.JJJJ oder JJJJ-MM-TT.",
                )

        # Regex check (applies to string, plz, and any typed field with a regex)
        if rule.regex:
            if not re.fullmatch(rule.regex, cell):
                return ValidationError(
                    row_index=row_index,
                    column_name=rule.name,
                    invalid_value=cell,
                    error_type="REGEX_VERLETZUNG",
                    fix_suggestion=rule.fix_suggestion or f"Wert muss dem Muster '{rule.regex}' entsprechen.",
                )

        # Codelist check
        if rule.codelist:
            # Создаем список разрешенных кодов в верхнем регистре и без пробелов
            allowed_codes_upper = [str(code).strip().upper() for code in rule.codelist]
            
            # Очищаем проверяемое значение ячейки
            clean_cell = cell.strip().upper()
            
            if clean_cell not in allowed_codes_upper:
                return ValidationError(
                    row_index=row_index,
                    column_name=rule.name,
                    invalid_value=cell,
                    error_type="UNGÜLTIGER_CODELISTEN_WERT",
                    fix_suggestion=rule.fix_suggestion or f"Erlaubte Werte: {', '.join(rule.codelist[:10])}...", 
                )

        return None
