# Beitrag leisten — Contributing Guide

Vielen Dank für Ihr Interesse, zum **XÖV-Prüfbaustein** beizutragen!
Bitte lesen Sie diese Anleitung, bevor Sie einen Pull Request einreichen.

---

## 🛠 Entwicklungsumgebung einrichten

```bash
# Repository forken und klonen
git clone https://github.com/<ihr-nutzername>/xoev-pruefbaustein.git
cd xoev-pruefbaustein

# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (neues Terminal)
cd frontend
npm install
npm run dev
```

---

## 📐 Architekturprinzipien (verbindlich)

Alle Beiträge müssen diese Prinzipien einhalten:

| Prinzip | Beschreibung |
|---|---|
| **Kein PII-Logging** | Zellinhalte oder ungültige Benutzerwerte dürfen niemals in Server-Logs erscheinen |
| **Kein Datenbankzugriff** | Alle Daten werden ausschließlich im flüchtigen RAM verarbeitet (`io.BytesIO`) |
| **Offline-First** | Keine externen CDNs, keine Google Fonts, keine API-Aufrufe an Dritte |
| **Deklarative Regeln** | Neue XÖV-Schemata kommen als JSON in `/rules` — kein Engine-Code ändern |
| **Barrierefreiheit** | BITV 2.0 / WCAG 2.1 AA: ARIA-Labels, Tastaturnavigation, Fokus-Indikatoren |
| **Deutsch im UI** | Alle Texte, Labels und Fehlermeldungen auf Deutsch |

---

## 🌿 Branch-Konvention

```
main          — stabiler Produktionszweig (geschützt)
feature/xyz   — neue Funktionen
fix/xyz       — Bugfixes
schema/xyz    — neue XÖV-Schemadateien
```

---

## ✅ Checkliste vor dem Pull Request

- [ ] Backend: `uvicorn app.main:app --reload` startet ohne Fehler
- [ ] Frontend: `npm run build` baut ohne TypeScript-Fehler
- [ ] Kein PII (Testdaten, echte Register-Dateien) im Commit enthalten
- [ ] Neue XÖV-Schemata: Namensschema `<standard>_<version>_compiled.json` einhalten
- [ ] UI-Änderungen: Tastaturnavigation und Fokus-Indikatoren funktionieren
- [ ] Commit-Nachricht auf Englisch oder Deutsch, beschreibend

---

## 🐛 Fehler melden (Issues)

Beim Melden eines Fehlers bitte angeben:
1. Betriebssystem und Browser-Version
2. Python- und Node.js-Version
3. Reproduktionsschritte
4. Erwartetes vs. tatsächliches Verhalten
5. **Keine echten Registerdaten** als Anhang — synthetische Beispieldaten verwenden

---

## 📄 Lizenz

Mit einem Beitrag stimmen Sie zu, dass Ihr Code unter der **EUPL 1.2** veröffentlicht wird.
