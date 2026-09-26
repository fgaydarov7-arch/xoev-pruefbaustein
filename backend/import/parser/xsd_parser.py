"""
xsd_parser.py — XSD-Syntaxanalyse für XÖV-Standards.

Öffentliche API:
  extract_codelist_from_appinfo(node)  — extrahiert (urn, version) aus xs:annotation
  XOVSchemaParser                      — parst XSD-Verzeichnisse, baut Typ-Index,
                                         extrahiert Codelisten-Bindungen
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from . import NS_XS, _find_child_by_local, _is_xoev_urn, _local_name
from .resolver import OASISCatalogResolver

log = logging.getLogger(__name__)


# ── Annotation-Extraktion ─────────────────────────────────────────────────────

def extract_codelist_from_appinfo(node: etree._Element) -> tuple[str, str]:
    """
    Extrahiert (urn, version) aus einem xs:annotation/xs:appinfo-Block.
    Gibt ("", "") zurück, wenn keine XÖV-Codelisten-Annotation gefunden.

    Unterstützte Muster (in Reihenfolge absteigender Häufigkeit):

    Muster A — XÖV 3.x Standardformat (häufigster Fall in XAusländer 26.11):
      <xs:appinfo>
        <codeliste><kennung>urn:de:xauslaender:codelist:...</kennung></codeliste>
        <versionCodeliste><version>4</version></versionCodeliste>
      </xs:appinfo>

    Muster B — XInneres-Format (kennung ohne versionCodeliste):
      <xs:appinfo>
        <codeliste><kennung>urn:xoev-de:xinneres:codeliste:geschlecht</kennung></codeliste>
      </xs:appinfo>

    Muster C — listURI-Attribut (fixed=) in xs:restriction:
      <xs:attribute name="listURI" fixed="urn:xoev-de:..."/>

    Muster D — generischer Fallback: beliebiges Element/Attribut mit URN-Wert
    """
    XS      = NS_XS
    appinfo = node.find(f"{{{XS}}}annotation/{{{XS}}}appinfo")
    if appinfo is None:
        return "", ""

    # -- A & B: <codeliste><kennung> ------------------------------------------
    for codeliste_el in appinfo.iter():
        if _local_name(codeliste_el) != "codeliste":
            continue
        kennung_el = _find_child_by_local(codeliste_el, "kennung")
        if kennung_el is None:
            continue
        urn = (kennung_el.text or "").strip()
        if not _is_xoev_urn(urn):
            continue

        version = ""
        version_container = _find_child_by_local(appinfo, "versionCodeliste")
        if version_container is not None:
            ver_el = _find_child_by_local(version_container, "version")
            if ver_el is not None:
                version = (ver_el.text or "").strip()
        if not version:
            ver_el = (
                _find_child_by_local(codeliste_el, "version")
                or _find_child_by_local(appinfo, "version")
            )
            if ver_el is not None:
                version = (ver_el.text or "").strip()

        return urn, version

    # -- C: xs:attribute[@name='listURI'][@fixed='urn:...'] -------------------
    for attr_el in node.iter(f"{{{XS}}}attribute"):
        if attr_el.get("name") == "listURI":
            fixed = attr_el.get("fixed", "")
            if _is_xoev_urn(fixed):
                return fixed.strip(), attr_el.get("listVersionID", "")

    # -- D: Generischer Fallback — Element oder Attribut mit URN-Wert ---------
    for descendant in appinfo.iter():
        for attr in ("urn", "URN", "kennung", "uri"):
            val = descendant.get(attr, "")
            if _is_xoev_urn(val):
                return val.strip(), descendant.get("version", "")
        text = (descendant.text or "").strip()
        if _is_xoev_urn(text):
            parent  = descendant.getparent()
            ver_el  = _find_child_by_local(parent, "version") if parent is not None else None
            return text, (ver_el.text or "").strip() if ver_el is not None else ""

    return "", ""


# ── XSD-Parser ────────────────────────────────────────────────────────────────

class XOVSchemaParser:
    """
    Parst XSD-Dateien eines XÖV-Standards, folgt xs:import/xs:include-Ketten
    (via OASIS Catalog) und baut einen globalen Typ-Index auf.

    Ablauf:
      1. parse_directory(xsd_dir)        — alle *.xsd einlesen + Typen indizieren
      2. resolve_codelist(type_ref)      — Typreferenz → (urn, version)
      3. extract_rules()                 — xs:element → Regeleinträge

    Jede Instanz hat einen isolierten Typ-Index — kein Übersprechen zwischen Standards.
    """

    def __init__(self, catalog: OASISCatalogResolver) -> None:
        self._catalog  = catalog
        self._parsed:  dict[str, Optional[etree._Element]] = {}
        self._type_idx: dict[str, tuple[etree._Element, str]] = {}
        self._parsing: set[str] = set()  # Zyklus-Schutz

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _make_parser(self) -> etree.XMLParser:
        """
        XMLParser mit registriertem Catalog-Resolver.
        resolve_entities=False schützt vor XXE (XML External Entity Injection).
        """
        p = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            recover=True,
        )
        p.resolvers.add(self._catalog)
        return p

    def parse_file(self, path: Path) -> Optional[etree._Element]:
        """
        Parst eine XSD-Datei und folgt rekursiv allen xs:import/xs:include-
        Referenzen. Zyklische Importe werden erkannt und übersprungen.
        Gibt den Root-Knoten zurück oder None bei Fehlern.
        """
        key = str(path.resolve())

        if key in self._parsed:
            return self._parsed[key]
        if key in self._parsing:
            log.debug("Zyklus erkannt, übersprungen: %s", path.name)
            return None
        if not path.exists():
            log.warning("XSD nicht gefunden: %s", path)
            self._parsed[key] = None
            return None

        self._parsing.add(key)
        try:
            root = etree.parse(str(path), self._make_parser()).getroot()
        except etree.XMLSyntaxError as exc:
            log.error("XML-Syntaxfehler in %s: %s", path.name, exc)
            self._parsed[key] = None
            return None
        except OSError as exc:
            log.error("I/O-Fehler beim Lesen von %s: %s", path.name, exc)
            self._parsed[key] = None
            return None
        finally:
            self._parsing.discard(key)

        self._parsed[key] = root
        self._index_types(root, path.name)
        self._follow_imports(root, path)
        return root

    def parse_directory(self, xsd_dir: Path) -> int:
        """Parst alle *.xsd-Dateien in einem Verzeichnis (nur erste Ebene)."""
        if not xsd_dir.is_dir():
            log.error("Verzeichnis nicht gefunden: %s", xsd_dir)
            return 0
        files = sorted(xsd_dir.glob("*.xsd"))
        log.info("Scanne %d XSD-Dateien in: %s", len(files), xsd_dir)
        for f in files:
            log.debug("  Parsing: %s", f.name)
            self.parse_file(f)
        ok = sum(1 for v in self._parsed.values() if v is not None)
        log.info("Erfolgreich geparst: %d / %d Dateien", ok, len(self._parsed))
        return ok

    # ── Import-Verfolgung ─────────────────────────────────────────────────────

    def _follow_imports(self, root: etree._Element, current: Path) -> None:
        """
        Liest xs:import und xs:include aus root und parst die referenzierten
        XSD-Dateien rekursiv. Auflösung: Catalog → relativer Pfad → skip.
        """
        XS = NS_XS
        for tag in (f"{{{XS}}}import", f"{{{XS}}}include"):
            for el in root.findall(tag):
                loc = el.get("schemaLocation", "").strip()
                if not loc:
                    continue

                resolved = self._catalog.locate(loc)
                if resolved is None:
                    # Relativer Pfad zur aktuellen Datei (xs:include).
                    # NICHT für absolute URLs versuchen — Path() wirft auf Windows
                    # OSError bei "https://..."-Strings.
                    if not loc.startswith(("http://", "https://", "ftp://", "//")):
                        try:
                            rel = (current.parent / loc).resolve()
                            resolved = rel if rel.exists() else None
                        except (ValueError, OSError):
                            pass

                if resolved:
                    self.parse_file(resolved)
                else:
                    log.debug("Import nicht aufgelöst (kein lokaler Match): %s", loc)

    # ── Typ-Index ─────────────────────────────────────────────────────────────

    def _index_types(self, root: etree._Element, source_file: str) -> None:
        """
        Indexiert alle top-level xs:complexType, xs:simpleType und xs:element.
        First-wins: früher geladene Dateien (Baukasten > Nachrichten) haben Vorrang.
        """
        XS = NS_XS
        indexable = {
            f"{{{XS}}}complexType",
            f"{{{XS}}}simpleType",
            f"{{{XS}}}element",
        }
        for child in root:
            if child.tag in indexable:
                name = child.get("name", "").strip()
                if name and name not in self._type_idx:
                    self._type_idx[name] = (child, source_file)

    # ── Codelisten-Auflösung ──────────────────────────────────────────────────

    def resolve_codelist(
        self,
        type_ref: str,
        _visited: set[str] | None = None,
    ) -> tuple[str, str]:
        """
        Verfolgt eine Typreferenz durch den Typ-Index bis zu einer
        Codelisten-Annotation. Gibt (urn, version) oder ("", "") zurück.

        Zyklusschutz: _visited speichert bereits besuchte Typnamen.
        """
        if _visited is None:
            _visited = set()

        # Namespace-Präfix entfernen: "xig:Code.Geschlecht" → "Code.Geschlecht"
        local = type_ref.split(":")[-1] if ":" in type_ref else type_ref

        if not local or local in _visited:
            return "", ""
        _visited.add(local)

        if local not in self._type_idx:
            return "", ""

        type_node, _ = self._type_idx[local]

        # Direkte Annotation am Typ-Knoten (häufigster Fall für Code.*)
        urn, ver = extract_codelist_from_appinfo(type_node)
        if urn:
            return urn, ver

        XS = NS_XS
        restriction = type_node.find(f".//{{{XS}}}restriction")
        if restriction is not None:
            base = restriction.get("base", "").strip()
            if base:
                urn, ver = self.resolve_codelist(base, _visited)
                if urn:
                    return urn, ver

            # listURI-Attribut in der Restriction (Muster C)
            for attr_el in restriction.findall(f"{{{XS}}}attribute"):
                if attr_el.get("name") == "listURI":
                    fixed = attr_el.get("fixed", "")
                    if _is_xoev_urn(fixed):
                        return fixed.strip(), ""

        # xs:complexContent → eingebettete Element-Typen verfolgen
        for child_el in type_node.iter(f"{{{XS}}}element"):
            child_type = child_el.get("type", "").strip()
            if child_type:
                urn, ver = self.resolve_codelist(child_type, _visited)
                if urn:
                    return urn, ver

        return "", ""

    # ── Regel-Extraktion ──────────────────────────────────────────────────────

    def extract_rules(self) -> dict[str, dict]:
        """
        Hauptextraktions-Pass: Für jedes geparste xs:element mit @name wird
        geprüft, ob es eine Codelisten-Bindung hat (direkt oder über Typen).

        Rückgabe: {element_name → {target_column, xoev_urn, required_version,
                                   source_schema}}
        """
        rules: dict[str, dict] = {}
        XS = NS_XS

        for abs_path, root in self._parsed.items():
            if root is None:
                continue

            source_file = Path(abs_path).name

            for element in root.iter(f"{{{XS}}}element"):
                name = element.get("name", "").strip()
                if not name:
                    continue  # ref= statt name= → kein neuer Name

                if name in rules:
                    continue  # First-wins

                # 1. Direkte Annotation am xs:element
                urn, ver = extract_codelist_from_appinfo(element)

                # 2. Annotation über Typreferenz (@type)
                if not urn:
                    type_ref = element.get("type", "").strip()
                    if type_ref:
                        urn, ver = self.resolve_codelist(type_ref)

                if urn:
                    rules[name] = {
                        "target_column":    name,
                        "xoev_urn":         urn,
                        "required_version": ver,
                        "source_schema":    source_file,
                    }

        log.info("Extrahierte Codelisten-Regeln: %d", len(rules))
        return dict(sorted(rules.items()))
