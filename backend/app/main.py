import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .engine import load_schema, read_headers, validate

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


# ── POST /preview ─────────────────────────────────────────────────────────────

@app.post("/preview")
async def preview_endpoint(file: UploadFile = File(...)) -> dict:
    """
    Read only the header row from an uploaded Excel file.
    Used by the frontend mapping UI to display file columns before validation.
    No row data is processed; no user data is retained.
    """
    file_bytes = await file.read(MAX_BYTES + 1)
    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Datei überschreitet die maximale Größe von 50 MB.")
    try:
        headers = read_headers(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        del file_bytes
    return {"headers": headers}


# ── GET /fields/{schema_id} ───────────────────────────────────────────────────

@app.get("/fields/{schema_id}")
def get_fields(schema_id: str) -> list[dict]:
    """
    Return a flat, sorted list of all fields in the given schema.
    Shape: [{key: str, label: str}]
    Used by the frontend mapping UI combobox (hundreds of entries).
    """
    try:
        schema = load_schema(schema_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    field_defs = schema.get("fields", {})
    result: list[dict] = []

    seen_keys: set[str] = set()

    if isinstance(field_defs, dict):
        for key, rule in field_defs.items():
            k     = str(key).strip().lower()
            short = rule.get("display_name_short") or ""
            long_ = rule.get("display_name_long")  or ""
            human = short or long_ or k
            label = f"{human} ({k})" if human != k else k
            result.append({"key": k, "label": label, "has_codelist": True})
            seen_keys.add(k)
    elif isinstance(field_defs, list):
        for rule in field_defs:
            key   = rule.get("name") or rule.get("target_column") or ""
            if not key:
                continue
            k     = str(key).strip().lower()
            short = rule.get("display_name_short") or ""
            human = short or k
            label = f"{human} ({k})" if human != k else k
            result.append({"key": k, "label": label, "has_codelist": True})
            seen_keys.add(k)

    # Include known_fields entries (XSD elements without a codelist)
    for raw_key in schema.get("known_fields", []):
        k = str(raw_key).strip().lower()
        if k and k not in seen_keys:
            result.append({"key": k, "label": k, "has_codelist": False})

    return sorted(result, key=lambda x: x["label"].lower())


# ── POST /validate ────────────────────────────────────────────────────────────

@app.post("/validate")
async def validate_endpoint(
    file:      UploadFile = File(...),
    schema_id: str        = Form(...),
    mapping:   str        = Form(default=""),
) -> dict:
    """
    Accept a multipart upload (file + schema_id + optional mapping JSON),
    run in-memory validation, and return a ValidationReport JSON object.

    mapping format: {"file_col_name": "schema_key" | null, ...}
      Columns mapped to null are dropped before validation.
      Columns absent from the mapping are validated as-is.
    """
    file_bytes = await file.read(MAX_BYTES + 1)
    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Datei überschreitet die maximale Größe von 50 MB.")

    try:
        schema = load_schema(schema_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    mapping_dict: dict | None = None
    if mapping:
        try:
            mapping_dict = json.loads(mapping)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Ungültiges Mapping-JSON.")

    t0 = time.perf_counter()
    try:
        report = validate(file_bytes, schema, mapping_dict or None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        log.exception("Unerwarteter Validierungsfehler für schema_id=%s", schema_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler bei der Validierung.")
    finally:
        del file_bytes

    log.info(
        "schema=%s  rows=%d  errors=%d  warnings=%d  time=%.3fs",
        schema_id,
        report["total_rows"],
        report["error_count"],
        report["warning_count"],
        time.perf_counter() - t0,
    )
    return report


# ── GET /health ───────────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}
