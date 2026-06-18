from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .engine import XovValidator
from .schemas import SchemaConfig, SchemaInfo, ValidationReport

# ---------------------------------------------------------------------------
# BSI-konformes Logging (kein PII)
# ---------------------------------------------------------------------------

class _PiiFilter(logging.Filter):
    """Sicherheitsfilter: verhindert versehentliches Loggen von PII in Nachrichten."""
    _BLOCKED_KEYS = frozenset({"value", "cell", "invalid_value", "row_content"})

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            for key in self._BLOCKED_KEYS:
                record.args.pop(key, None)
        return True


logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("xoev_validator")
logger.addFilter(_PiiFilter())

# ---------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="XÖV-Prüfbaustein API",
    description="Datenschutzkonforme Offline-Validierungs-Engine für XÖV-Metadaten (BSI-Grundschutz).",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

RULES_DIR = Path(__file__).parent.parent / "rules"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# ---------------------------------------------------------------------------
# Helper: schema loader
# ---------------------------------------------------------------------------

def _load_schema(schema_id: str) -> SchemaConfig:
    schema_file = RULES_DIR / f"{schema_id}.json"
    if not schema_file.exists() or schema_file.name.startswith("_"):
        raise HTTPException(status_code=404, detail=f"Schema '{schema_id}' nicht gefunden.")
    try:
        raw = json.loads(schema_file.read_text(encoding="utf-8"))
        return SchemaConfig(**raw)
    except Exception as exc:
        logger.error('"Fehler beim Laden des Schemas: %s"', schema_id)
        raise HTTPException(status_code=500, detail="Schema konnte nicht geladen werden.") from exc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get(
    "/schemas",
    response_model=list[SchemaInfo],
    summary="Verfügbare XÖV-Schemata abrufen",
    tags=["Schemata"],
)
def list_schemas() -> list[SchemaInfo]:
    """Scannt das /rules-Verzeichnis dynamisch und gibt alle verfügbaren Schemata zurück."""
    schemas: list[SchemaInfo] = []
    for path in sorted(RULES_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            cfg = SchemaConfig(**raw)
            schemas.append(SchemaInfo(
                schema_id=cfg.schema_id,
                schema_name=cfg.schema_name,
                version=cfg.version,
                xoev_standard=cfg.xoev_standard,
                description=cfg.description,
            ))
        except Exception:
            logger.warning('"Ungültige Schemadatei übersprungen: %s"', path.name)
    return schemas


@app.post(
    "/validate",
    response_model=ValidationReport,
    summary="CSV/Excel-Datei gegen ein XÖV-Schema validieren",
    tags=["Validierung"],
)
async def validate_file(
    file: UploadFile = File(..., description="CSV- oder Excel-Datei (max. 50 MB)"),
    schema_id: str = Form(..., description="ID des zu verwendenden XÖV-Schemas"),
) -> ValidationReport:
    t_start = time.perf_counter()

    # --- Dateigrößenprüfung (DoS-Schutz) ---
    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Datei überschreitet die maximale Größe von 50 MB.",
        )

    schema = _load_schema(schema_id)
    filename = file.filename or "upload.csv"

    try:
        validator = XovValidator(schema)
        report = validator.validate(file_bytes, filename)
    except Exception as exc:
        logger.error('"Validierungsfehler für Schema: %s"', schema_id)
        raise HTTPException(status_code=422, detail="Datei konnte nicht verarbeitet werden.") from exc
    finally:
        # Volatile bytes sofort dereferenzieren
        del file_bytes

    elapsed = round(time.perf_counter() - t_start, 4)
    logger.info(
        '{"schema_id": "%s", "rows_processed": %d, "error_count": %d, "duration_s": %s}',
        schema_id,
        report.total_rows,
        report.error_count,
        elapsed,
    )

    return report


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}
