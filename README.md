# XÖV-Prüfbaustein

**Datenschutzkonforme Offline-Validierungs-Engine für kommunale XÖV-Register**

---

## Überblick

Der XÖV-Prüfbaustein ist ein produktionsreifes, monolithisches Werkzeug für Sachbearbeiterinnen und Sachbearbeiter im öffentlichen Dienst. Er ermöglicht die lokale Validierung von CSV- und Excel-Dateien gegen offizielle XÖV-Schemata – vollständig offline, ohne Datenbankverbindung und ohne externe Netzwerkkommunikation.

**Kern-Merkmale:**

- **100 % air-gapped**: Kein CDN, keine Google Fonts, keine externen Abhängigkeiten zur Laufzeit
- **Datenschutz by Design**: Alle Daten werden ausschließlich im flüchtigen Arbeitsspeicher (`io.BytesIO`) verarbeitet – keine Persistenz, kein Caching, keine Logs mit personenbezogenen Inhalten
- **BSI-Grundschutz konform**: Dateigröße auf 50 MB begrenzt (DoS-Schutz), strukturiertes PII-freies Logging, UTF-8-Durchsetzung
- **BITV 2.0 / WCAG 2.1 AA**: Vollständig barrierefreie Benutzeroberfläche auf Deutsch
- **EUPL 1.2**: Lizenziert unter der European Union Public Licence

---

## Architektur: Universelle XÖV-Abdeckung durch JSON-Regelwerke

Das entscheidende Architekturmerkmal ist die **vollständige Trennung von Validierungs-Engine und Fachlogik**. Die Engine selbst enthält keinerlei XÖV-spezifisches Wissen – dieses ist ausschließlich in deklarativen JSON-Dateien im Verzeichnis `/backend/rules/` gespeichert.

### Neues XÖV-Schema hinzufügen (ohne Code-Änderung)

Um einen der über 30 weiteren XÖV-Standards (XBau, XRechnung, XJustiz, XKfz, XHochschule usw.) zu integrieren, genügt ein einziger Schritt:

```
/backend/rules/
└── xbau_2_0.json   ← Neue Datei ablegen, fertig.
```

Der Validator erkennt und lädt die neue Datei beim nächsten Start automatisch. Es sind **keinerlei Änderungen am Python-Code** erforderlich. Die Vorlage `_template_future_schema.json` beschreibt das vollständige JSON-Schema mit allen unterstützten Feldtypen und Validierungsregeln.

### Unterstützte Feldtypen

| Typ         | Beschreibung                                                       |
|-------------|--------------------------------------------------------------------|
| `string`    | Freier Text; kombinierbar mit `regex` und/oder `codelist`          |
| `date`      | Datum; Engine parst `TT.MM.JJJJ` und `JJJJ-MM-TT` automatisch    |
| `steuer_id` | 11-stellige Steuer-ID; BZSt-Prüfziffer-Algorithmus automatisch     |
| `iban`      | IBAN; Modulo-97-Prüfung (ISO 13616) automatisch                    |
| `plz`       | Deutsche PLZ; verwenden Sie zusätzlich `"regex": "^[0-9]{5}$"`    |

---

## Enthaltene XÖV-Schemata

| Datei                    | Standard     | Behörde               |
|--------------------------|--------------|-----------------------|
| `xmeld_basic.json`       | XMeld        | Bürgeramt / EWO       |
| `xgewerbe_2_1.json`      | XGewerbe 2.1 | Ordnungsamt           |
| `xauslaender_core.json`  | XAusländer   | Ausländerbehörde      |

---

## Lokaler Betrieb

### Voraussetzungen

- Python 3.11+
- Node.js 20+ und npm

### Backend starten

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Die API-Dokumentation ist unter [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs) erreichbar.

### Frontend starten (Entwicklungsmodus)

```bash
cd frontend
npm install
npm run dev
```

Die Anwendung ist unter [http://localhost:5173](http://localhost:5173) erreichbar.

### Frontend als statisches Bundle erstellen

```bash
cd frontend
npm run build
```

Das fertige Bundle im Verzeichnis `frontend/dist/` kann auf jedem lokalen Webserver (z. B. Apache/XAMPP) ohne weitere Abhängigkeiten betrieben werden.

---

## Sicherheitshinweise

| Maßnahme                         | Umsetzung                                                                                   |
|----------------------------------|---------------------------------------------------------------------------------------------|
| Kein PII in Logs                 | Strukturierter Logger mit `_PiiFilter`; nur Metadaten (Zeitstempel, Schema-ID, Zeilenanzahl, Fehleranzahl, Dauer) |
| CSV-Injection-Schutz             | Frontend-Export setzt `'`-Präfix vor Zellen, die mit `=`, `+`, `-`, `@` beginnen           |
| UTF-8 BOM im Export              | Excel-kompatibler Download mit `﻿`-Präfix; Umlaute bleiben korrekt dargestellt         |
| DOM-Guardrail                    | Tabelle zeigt maximal 500 Fehlereinträge; vollständiger Bericht im CSV-Export               |
| Dateigröße begrenzt              | FastAPI lehnt Uploads über 50 MB mit HTTP 413 ab                                            |
| In-Memory-Verarbeitung           | `io.BytesIO` – keine temporären Dateien auf der Festplatte                                  |

---

## Lizenz

Lizenziert unter der **European Union Public Licence 1.2 (EUPL-1.2)**.  
Siehe [https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12).
