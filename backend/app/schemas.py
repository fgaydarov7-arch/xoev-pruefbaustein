from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class FieldRule(BaseModel):
    name: str
    required: bool = True
    type: str
    regex: Optional[str] = None
    codelist: Optional[list[str]] = None
    description: Optional[str] = None
    fix_suggestion: Optional[str] = None


class SchemaConfig(BaseModel):
    schema_id: str
    schema_name: str
    version: str
    xoev_standard: str
    description: Optional[str] = None
    fields: list[FieldRule]


class SchemaInfo(BaseModel):
    schema_id: str
    schema_name: str
    version: str
    xoev_standard: str
    description: Optional[str] = None


class ValidationError(BaseModel):
    row_index: int = Field(..., description="1-based Zeilenindex im CSV (exkl. Header)")
    column_name: str
    invalid_value: str
    error_type: str
    fix_suggestion: str


class ValidationReport(BaseModel):
    schema_id: str
    schema_name: str
    total_rows: int
    error_count: int
    success_rate: float = Field(..., description="Anteil fehlerfreier Zeilen in Prozent (0–100)")
    errors: list[ValidationError]
