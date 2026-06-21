import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .engine import load_schema, validate

# ── Logging (BSI: no PII in log output) ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("xoev")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="XÖV-Prüfbaustein API",
    description="Datenschutzkonforme Offline-Validierung für XÖV-Metadaten.",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

RULES_DIR  = Path(__file__).parent.parent / "rules"
MAX_BYTES  = 50 * 1024 * 1024  # 50 MB – BSI DoS guard


# ── GET /schemas ──────────────────────────────────────────────────────────────

@app.get("/schemas")
def list_schemas() -> list[dict]:
    """
    Scan the /rules directory and return metadata for every valid JSON schema.
    Files starting with '_' (templates) are skipped.
    """
    result = []
    for path in sorted(RULES_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            result.append({
                "schema_id":     data["schema_id"],
                "schema_name":   data.get("schema_name", ""),
                "version":       data.get("version", ""),
                "xoev_standard": data.get("xoev_standard", ""),
                "description":   data.get("description"),
            })
        except Exception:
            log.warning("Schemadatei übersprungen (ungültig): %s", path.name)
    return result


# ── POST /validate ────────────────────────────────────────────────────────────

@app.post("/validate")
async def validate_endpoint(
    file:      UploadFile = File(...),
    schema_id: str        = Form(...),
) -> dict:
    """
    Accept a multipart upload (file + schema_id), run in-memory validation,
    and return a ValidationReport JSON object for the frontend.
    """
    # Read file bytes with size guard (one extra byte to detect over-limit)
    file_bytes = await file.read(MAX_BYTES + 1)
    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Datei überschreitet die maximale Größe von 50 MB.")

    # Load the JSON rules file
    try:
        schema = load_schema(schema_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Run validation engine
    t0 = time.perf_counter()
    try:
        report = validate(file_bytes, schema)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        log.exception("Unerwarteter Validierungsfehler für schema_id=%s", schema_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler bei der Validierung.")
    finally:
        del file_bytes  # drop from volatile memory immediately

    log.info(
        "schema=%s  rows=%d  errors=%d  time=%.3fs",
        schema_id,
        report["total_rows"],
        report["error_count"],
        time.perf_counter() - t0,
    )
    return report


# ── GET /health ───────────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}
