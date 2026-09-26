"""
genericode.py — Parst OASIS Genericode 1.0 Codelisten-Dateien.

Öffentliche API:
  GenericodeIndex          — scannt Verzeichnisse, baut URN → Pfad-Index auf
  parse_genericode_codes   — extrahiert Code-Werte aus einer XML-Datei
  enrich_rules_with_codes  — hängt allowed_codes an Regel-Dicts
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from . import NS_CL3, NS_CL4

log = logging.getLogger(__name__)


# ── Code-Spalten-Erkennung ────────────────────────────────────────────────────

def _find_recommended_key_column(root: etree._Element) -> str:
    """
    Ermittelt die Id der empfohlenen Code-Spalte aus dem ColumnSet.

    Priorisierung:
      1. Key mit Annotation <xoev-cl-3:empfohleneCodeSpalte/> (XInneres-Format)
         oder <xoev-cl-4:recommendedKeyColumn/>               (XAusländer-Format)
      2. Erster Key im ColumnSet als Fallback
    """
    recommended_tags = {
        f"{{{NS_CL3}}}empfohleneCodeSpalte",
        f"{{{NS_CL4}}}recommendedKeyColumn",
    }
    for key in root.iter("Key"):
        if any(d.tag in recommended_tags for d in key.iter()):
            col_ref = key.find("ColumnRef")
            if col_ref is not None:
                return col_ref.get("Ref", "")
    # Fallback: erster Key
    first_key = root.find(".//Key")
    if first_key is not None:
        col_ref = first_key.find("ColumnRef")
        if col_ref is not None:
            return col_ref.get("Ref", "")
    return ""


# ── Code-Extraktion ───────────────────────────────────────────────────────────

def parse_genericode_codes(path: Path) -> list[str]:
    """
    Extrahiert alle Code-Werte aus einer Genericode-XML-Datei (OASIS Genericode 1.0).

    Datei-Struktur:
      <gc:CodeList>
        <ColumnSet>
          <Key><ColumnRef Ref="CodeId"/></Key>
        </ColumnSet>
        <SimpleCodeList>
          <Row>
            <Value ColumnRef="CodeId">
              <SimpleValue>01</SimpleValue>
            </Value>
          </Row>
        </SimpleCodeList>
      </gc:CodeList>

    Hinweis: Innere Elemente (Row, Value, SimpleValue, Key) liegen in KEINEM Namespace;
    nur das Root-Element <gc:CodeList> trägt den gc:-Namespace.
    """
    try:
        root = etree.parse(str(path)).getroot()
    except (etree.XMLSyntaxError, OSError) as exc:
        log.warning("Genericode Parse-Fehler (%s): %s", path.name, exc)
        return []

    code_col_id = _find_recommended_key_column(root)
    if not code_col_id:
        first_col = root.find(".//Column")
        code_col_id = first_col.get("Id", "") if first_col is not None else ""

    if not code_col_id:
        log.warning("Keine Code-Spalte gefunden in: %s", path.name)
        return []

    codes: list[str] = []
    for row in root.iter("Row"):
        for val in row:
            if val.get("ColumnRef") == code_col_id:
                sv = val.find("SimpleValue")
                if sv is not None and sv.text:
                    text = sv.text.strip()
                    if text:
                        codes.append(text)
                break  # pro Row nur einen Treffer

    return codes


# ── Index ─────────────────────────────────────────────────────────────────────

class GenericodeIndex:
    """
    Scannt *.xml-Codelisten-Dateien in den angegebenen Verzeichnissen,
    liest nur <Identification><CanonicalUri> via iterparse (ohne vollen DOM),
    und baut einen schnellen URN → Path Lookup-Index auf.

    Unterstützt mehrere Verzeichnisse gleichzeitig.
    First-wins: bei doppelter URN gewinnt die zuerst gefundene Datei.
    """

    def __init__(self, *codelisten_dirs: Path) -> None:
        self._index:       dict[str, Path] = {}
        self.total_scanned = 0
        self.total_indexed = 0

        for d in codelisten_dirs:
            if not d.is_dir():
                log.warning("Codelisten-Verzeichnis nicht gefunden: %s", d)
                continue
            for xml_file in sorted(d.glob("*.xml")):
                self.total_scanned += 1
                try:
                    uri = self._read_canonical_uri(xml_file)
                    if uri and uri not in self._index:
                        self._index[uri] = xml_file
                        self.total_indexed += 1
                except Exception as exc:
                    log.debug("Index-Fehler (%s): %s", xml_file.name, exc)

        log.info(
            "Genericode-Index: %d / %d Dateien indiziert",
            self.total_indexed, self.total_scanned,
        )

    @staticmethod
    def _read_canonical_uri(path: Path) -> str:
        """Liest nur CanonicalUri via iterparse — speichereffizient auch bei großen Dateien."""
        for _, el in etree.iterparse(str(path), events=("end",), tag="CanonicalUri"):
            return (el.text or "").strip()
        return ""

    def locate(self, urn: str) -> Optional[Path]:
        """Gibt den Dateipfad für die gegebene URN zurück, oder None."""
        return self._index.get(urn)


# ── Anreicherung ──────────────────────────────────────────────────────────────

def enrich_rules_with_codes(
    rules: dict[str, dict],
    index: GenericodeIndex,
) -> tuple[dict[str, dict], int, int]:
    """
    Ergänzt jeden Regeleintrag um 'allowed_codes'.

    - URN im GenericodeIndex vorhanden  → Codes parsen und einbetten
    - URN nicht gefunden                → WARNING loggen, allowed_codes = []
    - URN leer (kein Codelisten-Feld)   → allowed_codes = [] (kein Log-Rauschen)

    Gibt zurück: (angereicherte_regeln, anzahl_gefunden, anzahl_nicht_gefunden)
    """
    found     = 0
    not_found = 0
    enriched: dict[str, dict] = {}

    for name, rule in rules.items():
        urn  = rule.get("xoev_urn", "")
        path = index.locate(urn) if urn else None

        if path:
            codes = parse_genericode_codes(path)
            found += 1
            log.debug("  [OK] %-55s %3d Codes  [%s]", urn, len(codes), path.name)
        else:
            codes = []
            not_found += 1
            if urn:
                log.warning("Codeliste nicht auf Disk: %s", urn)

        enriched[name] = {**rule, "allowed_codes": codes}

    return enriched, found, not_found
