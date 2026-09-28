# XÖV-Prüfbaustein — XÖV Validation Console

> **Datenschutzkonforme Offline-Validierung von XÖV-Registerdaten für den öffentlichen Dienst**

## License
Copyright © 2026 Farid Gaydarov
GitHub: https://github.com/fgaydarov7-arch
This project is licensed under the Apache License, Version 2.0.
You may obtain a copy of the License at:
https://www.apache.org/licenses/LICENSE-2.0
See the [LICENSE](LICENSE) file for the full license text.
SPDX-License-Identifier: Apache-2.0
[![BSI-Grundschutz](https://img.shields.io/badge/BSI-Grundschutz%20konform-003366.svg)]()
[![BITV 2.0](https://img.shields.io/badge/Barrierefreiheit-BITV%202.0%20AA-green.svg)]()
[![Stack](https://img.shields.io/badge/Stack-Python%203.11%20%7C%20FastAPI%20%7C%20React%2019-informational.svg)]()

---

## 📋 Beschreibung

Der **XÖV-Prüfbaustein** ist ein schlankes, vollständig offline-fähiges Werkzeug für kommunale Sachbearbeiter im öffentlichen Dienst. Es ermöglicht die lokale Validierung von CSV- und Excel-Dateien gegen offizielle XÖV-Schemata (XRepository) — ohne Internetverbindung, ohne Datenbank und ohne dass personenbezogene Daten das Gerät verlassen.

**Kernprinzip:** Alle hochgeladenen Daten werden ausschließlich im flüchtigen Arbeitsspeicher (`io.BytesIO`) verarbeitet und nach der Validierungsantwort sofort verworfen. Kein Logging von PII, kein Caching, keine externe Abhängigkeit.

---

## ✨ Funktionsumfang

| Feature | Details |
|---|---|
| 🗂 **Multi-Schema-Unterstützung** | XAusländer 26.11, XMeld 26.11 — erweiterbar durch JSON-Drop in `/rules` |
| 📊 **Interaktive Dateivorschau** | Tabellarische Darstellung mit Fehler-Highlighting auf Zellebene |
| 🔗 **Spalten-Mapping** | Manuelle Zuordnung von Dateispalten zu XÖV-Feldern per Combobox |
| ✅ **3-stufige Validierung** | Codelisten → Known Fields → NICHT_IM_PROFIL (amber Hinweis) |
| 📥 **Korrekturbericht-Export** | CSV-Download mit UTF-8-BOM (Excel-kompatibel) + Formel-Sanitisierung |
| 🔍 **Fehlerfilter & Paginierung** | Nur-Fehlerzeilen-Modus, konfigurierbare Seitengröße |
| ♿ **Barrierefreiheit** | BITV 2.0 / WCAG 2.1 AA — Tastaturnavigation, ARIA-Labels, Fokus-Indikatoren |
| 🛡 **BSI-Grundschutz** | 50 MB DoS-Limit, kein PII-Logging, CSV-Injection-Schutz |

---

## 🏗 Technologie-Stack

**Backend**
- Python 3.11+
- FastAPI 0.111 + Uvicorn
- Pandas 2.2 (In-Memory-Verarbeitung)
- Pydantic v2

**Frontend**
- React 19 + TypeScript
- Vite (Build-Tool)
- Tailwind CSS (Corporate Design Bund)
- Lucide-React (lokal gebundelt, kein CDN)

---

## 📁 Projektstruktur

```
xoevpruefbaustein.local/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI-Routen (/schemas, /fields, /validate, /preview)
│   │   ├── engine.py        # Validierungs-Engine (In-Memory, 3-stufige Prüfung)
│   │   └── __init__.py
│   ├── rules/               # Deklarative JSON-Validierungsprofile
│   │   ├── xauslaender_26.11_compiled.json
│   │   └── xmeld_26.11_compiled.json
│   ├── xrepository/         # Originale XSD-Quelldateien (XRepository-Spieglung)
│   ├── requirements.txt
│   └── !/                   # Hilfsskripte (build_xauslaender_schema.py, add_known_fields.py)
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Zentrale State-Verwaltung
│   │   ├── api.ts            # Fetch-Wrapper für Backend-API
│   │   └── components/
│   │       ├── FileUploader.tsx   # Drag-&-Drop, ARIA-konform
│   │       ├── ResultTable.tsx    # Datenvorschau-Grid mit Mapping-UI
│   │       ├── StatsCard.tsx      # Validierungsstatistik-Kacheln
│   │       └── ColumnMapper.tsx   # Spalten-Zuordnungs-Komponente
│   └── package.json
└── CLAUDE.md                # Projektdokumentation für KI-Assistenten
```

---

## 🚀 Lokale Installation

### Voraussetzungen

- Python **3.11** oder neuer
- Node.js **18** oder neuer
- npm 9+

### 1. Repository klonen

```bash
git clone https://github.com/<ihr-nutzername>/xoev-pruefbaustein.git
cd xoev-pruefbaustein
```

### 2. Backend einrichten

```bash
cd backend

# Virtuelle Umgebung erstellen und aktivieren
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux / macOS:
# source .venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Backend starten (Port 8000)
.venv\Scripts\uvicorn app.main:app --reload --port 8000
# Linux/macOS:
# uvicorn app.main:app --reload --port 8000
```

Der API-Server ist erreichbar unter: **http://127.0.0.1:8000**
Interaktive Dokumentation: **http://127.0.0.1:8000/api/docs**

### 3. Frontend einrichten

Neues Terminal öffnen:

```bash
cd frontend

# Abhängigkeiten installieren
npm install

# Entwicklungsserver starten (Port 5173)
npm run dev
```

Die Anwendung ist erreichbar unter: **http://localhost:5173**

### 4. Produktions-Build (optional)

```bash
cd frontend
npm run build
# Statische Dateien liegen dann in frontend/dist/
```

---

## ➕ Neues XÖV-Schema hinzufügen

Das System ist vollständig deklarativ. Kein Enginecode muss geändert werden:

1. Neue JSON-Datei in `backend/rules/` ablegen (Namensschema: `<standard>_<version>_compiled.json`)
2. Backend neu starten — das neue Schema erscheint automatisch in der Schemaauswahl

Die JSON-Struktur orientiert sich an den bestehenden Schemadateien. Ein kommentiertes Template liegt in `backend/!/rules - Kopie/_template_future_schema.json`.

---

## 🔐 Datenschutz & Sicherheit

- **Keine Datenbank** — alle Verarbeitungen laufen vollständig im RAM
- **Kein PII-Logging** — Protokoll enthält ausschließlich Metadaten (Zeitstempel, Schema-ID, Zeilenanzahl, Fehleranzahl)
- **Offline-fähig** — kein CDN, keine Google Fonts, keine externen Abhängigkeiten
- **50 MB Upload-Limit** — DoS-Schutz für kommunale Hardware (BSI-Grundschutz)
- **CSV-Injection-Schutz** — Formel-Sanitisierung beim Korrekturbericht-Export (`=`, `+`, `-`, `@` werden mit `'` präfigiert)

---

## 📄 Lizenz

Lizenziert unter der **European Union Public Licence 1.2 (EUPL-1.2)**.
Siehe [EUPL-Text](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) für Details.
