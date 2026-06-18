XÖV-Prüfbaustein

# ROLE & CONTEXT
You are an expert Enterprise Solutions Architect, Certified BSI-Grundschutz Specialist, and Senior Full-Stack Developer specializing in German Gov-Tech, XÖV standards (XRepository), and strict data privacy compliance (GDPR/DSGVO).

We are building a production-ready, monolithic-codebase "XÖV-Metadata-Validator" designed as a "last-mile" offline desktop/intranet tool for German municipal clerks (öffentlicher Dienst). The application allows users to upload local CSV/Excel registries, validates them against official XÖV schemas strictly in-memory, highlights specific validation failures, and provides a downloadable corrected report.

# CORE ARCHITECTURAL PRINCIPLES
1. Stateless Operation (Data Privacy First): No database allowed. Data must be processed entirely inside volatile memory (using Python's `io.BytesIO`). No user data must ever be cached, logged, or written to disk.
2. Compliance & Accessibility: The UI must be in German (Deutsch). Contrast, labels, and focus states must comply with BITV 2.0 (WCAG 2.1 AA) standards for government employees.
3. Open Source Ready: Fully compliant with EUPL 1.2 (European Union Public Licence) standards.
4. Robustness: Handle edge cases gracefully, such as case-insensitive column headers, diverse German date formats, and preserved representation of German Umlauts (ä, ö, ü, ß) via strict UTF-8 enforcement.
5. Future-Proof Extensibility: The validation engine must be entirely driven by declarative JSON rule files. Adding a new XÖV standard must only require dropping a new JSON file into the `/rules` directory—no engine code changes allowed.

# BSI-GRUNDSCHUTZ & ÖD SECURITY HARDENING
1. Memory-Safe File Processing:
   - Implement strict file size restrictions in FastAPI (Max 50MB) to protect municipal hardware from Denial-of-Service (DoS).
   - Design the validation engine to stream/handle tabular data safely without causing Out-of-Memory (OOM) exceptions.
2. GDPR-Compliant Logging (No PII):
   - Configure Python's structured logger to record operation metadata only (timestamp, execution time, schema_id, rows_processed, error_count).
   - Strictly FORBID logging of any cell contents or invalid user values into server logs. Person-identifiable data (PII) must only exist in runtime volatile memory and the direct JSON response.
3. CSV-Injection Prevention (Formula Sanitization):
   - When generating the "Korrektur-CSV" for download, the frontend must sanitize cell values. If a value begins with unsafe spreadsheet characters (=, +, -, @), prepend it with a single quote (') to neutralize execution in Microsoft Excel.
4. Air-Gapped/Offline Assurance:
   - The React frontend bundle must be 100% self-contained. Zero external CDNs, Zero third-party web fonts (Google Fonts), and all icons must be bundled via local svg/lucide-react imports. No external internet dependency is permitted.
5. DOM Performance Guardrails:
   - The UI table must handle large validation failure responses without locking the browser main thread. Cap the visible error rows in the HTML DOM to the first 500 records and add an informational banner stating that the remaining errors are accessible inside the comprehensive CSV export.

# WORKSPACE STRUCTURE TO GENERATE
You must generate the complete, production-ready code for ALL files specified in the structure below. Do NOT use placeholders, `// TODO` comments, or truncated snippets. Write fully realized business logic.

/xoevpruefbaustein.local
 ├── README.md
 ├── /backend
 │    ├── requirements.txt
 │    ├── /app
 │    │    ├── __init__.py
 │    │    ├── main.py
 │    │    ├── engine.py
 │    │    └── schemas.py
 │    └── /rules
 │         ├── xmeld_basic.json
 │         ├── xgewerbe_2_1.json
 │         ├── xauslaender_core.json
 │         └── _template_future_schema.json
 └── /frontend
      ├── package.json
      └── /src
           ├── App.tsx
           ├── api.ts
           └── /components
                ├── FileUploader.tsx
                ├── ResultTable.tsx
                └── StatsCard.tsx

---

## DETAILED COMPONENT SPECIFICATIONS

### 1. BACKEND (Python 3.11+, FastAPI, Pandas, Pydantic v2)

* `backend/requirements.txt`: Modern Python stack: `fastapi`, `uvicorn`, `pandas`, `pydantic`, `python-multipart`, and `openpyxl`.
* `backend/rules/`: Create 3 real-world XÖV rulesets plus a future-proof structural blueprint.
    * `xmeld_basic.json` (Bürgeramt): Fields for `Identifikationsnummer` (type: `steuer_id`), `Geburtsdatum` (type: `date`), `Anschrift_PLZ` (type: `plz`, regex: `^[0-9]{5}$`).
    * `xgewerbe_2_1.json` (Ordnungsamt): Fields for `Gemeindeschluessel` (type: `string`, regex: `^[0-9]{8}$`), `Gewerbe_Art` (type: `string`, codelist: `["Hauptniederlassung", "Zweigniederlassung", "Unselbständige Zweigstelle"]`).
    * `xauslaender_core.json` (Ausländerbehörde): Fields for `Geschlecht` (type: `string`, codelist: `["männlich", "weiblich", "divers", "unbestimmt"]`), `Staatsangehoerigkeit` (type: `string`, regex: `^[A-Z]{3}$`).
    * `_template_future_schema.json`: A thoroughly documented, structure-only JSON file showing how a developer can map any of the remaining 30+ XÖV standards (e.g., XBau, XRechnung) into this ecosystem.
* `backend/app/schemas.py`: Pydantic v2 models representing the dynamic Rules, JSON configurations, and the explicit `ValidationReport` output (`total_rows`, `error_count`, `success_rate`, and a list of detailed error objects containing `row_index`, `column_name`, `invalid_value`, `error_type`, `fix_suggestion`).
* `backend/app/engine.py`: Implement the `XovValidator` class.
    * **Checksum Logic**: Write explicit validation functions for:
        1. German Tax ID (`Steuer_ID` / `Identifikationsnummer`) using the official German 11-digit modulo verification algorithm (Prüfziffernberechnung nach dem Bundeszentralamt für Steuern).
        2. `IBAN` checksum validation (Modulo 97 processing) to catch typing errors early.
    * **Flexible Mapping & Pandas Float Fix**: Headers must map case-insensitively. Safely intercept and fix cases where Pandas interprets a code or postal code as a float (e.g., converting `42000.0` or `04109.0` back into safe strings without trimming leading zeros like `04109`).
    * **Date Parsing**: Safely parse German standard format (`DD.MM.YYYY`) and standard ISO (`YYYY-MM-DD`).
* `backend/app/main.py`: FastAPI routes with custom logging setup conforming to the BSI specifications.
    * `GET /schemas`: Dynamically scans the `/rules` directory (skipping the template) and returns an array of available schemas.
    * `POST /validate`: Accepts `Multipart/form-data` file and `schema_id`. Limits payload to 50MB. Process data dynamically in-memory.

### 2. FRONTEND (React 19, Vite, TypeScript, Tailwind CSS, Lucide-React)

* `frontend/package.json`: Configured for standard static client build via Vite.
* `frontend/src/api.ts`: API handler using standard browser fetch targeting local networking environments.
* `frontend/src/components/FileUploader.tsx`: Accessible drag-and-drop element containing proper ARIA roles (`role="button"`, `tabIndex={0}`) and handling keyboard triggers (`Space`/`Enter`) for screen readers (BITV 2.0 / WCAG 2.1 compliance).
* `frontend/src/components/StatsCard.tsx`: Summary display blocks showing "Zeilen Gesamt", "Gefundene Fehler" (red alert design if > 0), and "Erfolgsquote".
* `frontend/src/components/ResultTable.tsx`: Tabular reporting grid highlighting failures. Contains DOM guardrails (max 500 rows displayed) and an **Export Button**: Creates a new downloadable *Korrektur-CSV* locally in the browser. Crucial requirement: Must inject a UTF-8 Byte Order Mark (BOM: `\uFEFF`) at the beginning of the file so that German Microsoft Excel opens it immediately with preserved Umlauts, and applies the CSV-formula sanitization prefix (`'`).
* `frontend/src/App.tsx`: Central state management orchestrating standard state-flows wrapped in a clean, authoritative, trustful German administrative design scheme (deep corporate blues, slate backgrounds, focused borders).

### 3. DOCUMENTATION

* `README.md`: Written entirely in **German**, highlighting the architectural capacity to cover 100% of German XÖV standards simply by dropping new JSON configurations into the `/rules` block, showcasing its absolute air-gapped security model, BSI compliance, and local running instructions without orchestration.

Please write complete, production-grade files now.
## Critical Token Saving Rules
DO NOT EVER scan, index, count files, or run terminal commands (like PowerShell `Get-ChildItem`, `grep`, `find`) inside these directories:
- .git/, .github/, .vscode/, .idea/
- node_modules/, frontend/node_modules/
- frontend/dist/, frontend/build/

## Output Rules for Token Saving
- NEVER rewrite the entire file if you are making small changes.
- Use code diffs or partial code blocks with placeholders like `// ... existing code ..`.
- Provide only the modified methods, functions, or lines that need to be changed.
- When checking git status, always use flags to keep it short: `git status -s`
- NEVER run `git log` without limiting the output, use `git log -n 3 --oneline`
- If you are searching for a file or a bug, limit your initial search depth to 2 levels. Do not scan nested directories recursively unless explicitly guided by the user.