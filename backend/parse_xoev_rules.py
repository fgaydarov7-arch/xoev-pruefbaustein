#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_xoev_rules.py — Enterprise XÖV Schema Parser
====================================================
Generiert rules_xauslaender.json aus den XSD-Schemata des XAusländer-Standards.

Auflösungskette (Beispiel: Feld "Geschlecht"):
  xauslaender-baukasten.xsd
    xs:element name="geschlecht" type="xig:Code.Geschlecht"
      -> xs:import schemaLocation="http://www.osci.de/xinneres/geschlecht/1/..."
      -> catalog.xml -> xöv-registry/xinneres/26.11/xsd/xinneres-geschlecht.xsd
      -> xs:complexType name="Code.Geschlecht"
        -> <xs:appinfo><codeliste><kennung>urn:xoev-de:xinneres:codeliste:geschlecht
          -> Eintrag in rules_xauslaender.json

Aufruf (aus dem Verzeichnis xrepository/):
    pip install lxml
    python parse_xoev_rules.py [--verbose]

Ausgabe:
    xrepository/rules_xauslaender.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from lxml import etree

# --- Konstanten ---------------------------------------------------------------

NS_XS      = "http://www.w3.org/2001/XMLSchema"
NS_CATALOG = "urn:oasis:names:tc:entity:xmlns:xml:catalog"
# Genericode-Namespaces (Codelisten-XML)
NS_GC      = "http://docs.oasis-open.org/codelist/ns/genericode/1.0/"
NS_CL3     = "http://xoev.de/schemata/genericode/3"   # empfohleneCodeSpalte
NS_CL4     = "http://xoev.de/schemata/genericode/4"   # recommendedKeyColumn

# Bekannte URN-Präfixe in XÖV-Annotationen
_XOEV_URN_PREFIXES = (
    "urn:xoev-de:",
    "urn:de:xauslaender:",
    "urn:de:bund:",
)

# --- Logging ------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)-8s] %(message)s"
    logging.basicConfig(stream=sys.stderr, level=level, format=fmt, datefmt="%H:%M:%S")

log = logging.getLogger(__name__)

# --- OASIS XML Catalog Resolver -----------------------------------------------

class OASISCatalogResolver(etree.Resolver):
    """
    Liest catalog.xml (OASIS XML Catalog 1.1) und übersetzt externe URIs in
    lokale Dateipfade.  Wird in zwei Modi genutzt:
      1. Als lxml.etree.Resolver — lxml ruft resolve() bei externen Ressourcen auf.
      2. Direkt via locate(url) — für manuelle xs:import-Verfolgung im Parser.

    Unterstützte Katalog-Direktiven:
      <system>       — exakte systemId -> lokale URI
      <uri>          — exakte URI -> lokale URI
      <rewriteSystem> — Präfix-Umschreibung für systemId (längster Treffer)
      <rewriteURI>   — Präfix-Umschreibung für URI
      <nextCatalog>  — Ketten-Kataloge (mit Zyklus-Schutz)
    """

    def __init__(self, catalog_path: Path, fallback_dirs: list[Path] | None = None) -> None:
        super().__init__()
        self._base_dir = catalog_path.parent.resolve()
        # Exakte Abbildungen: url -> absoluter Pfad
        self._exact: dict[str, Path] = {}
        # Präfix-Abbildungen: [(prefix, base_path)] sortiert nach Länge desc
        self._rewrites: list[tuple[str, Path]] = []
        # Fallback-Verzeichnisse für Dateiname-only Suche
        self._fallback_dirs: list[Path] = fallback_dirs or []
        # Zyklusschutz beim Laden von <nextCatalog>
        self._loaded: set[str] = set()

        self._load_catalog(catalog_path)
        log.info(
            "Catalog geladen: %d exakte Einträge | %d Rewrite-Regeln | %d Fallback-Dirs",
            len(self._exact), len(self._rewrites), len(self._fallback_dirs),
        )

    # -- Katalog laden ---------------------------------------------------------

    def _load_catalog(self, path: Path, base: Path | None = None) -> None:
        abs_path = str(path.resolve())
        if abs_path in self._loaded:
            return
        self._loaded.add(abs_path)

        if not path.exists():
            log.warning("Katalog-Datei nicht gefunden: %s", path)
            return

        base = base or path.parent.resolve()
        try:
            root = etree.parse(str(path)).getroot()
        except etree.XMLSyntaxError as exc:
            log.error("catalog.xml Parse-Fehler (%s): %s", path.name, exc)
            return

        for el in root.iter():
            local = _local_name(el)

            if local == "system":
                sys_id = el.get("systemId", "")
                uri    = el.get("uri", "")
                if sys_id and uri:
                    self._exact[sys_id] = (base / uri).resolve()

            elif local == "uri":
                name = el.get("name", "")
                uri  = el.get("uri", "")
                if name and uri:
                    self._exact[name] = (base / uri).resolve()

            elif local == "rewriteSystem":
                prefix = el.get("systemIdStartString", "")
                repl   = el.get("rewritePrefix", "")
                if prefix and repl:
                    self._rewrites.append((prefix, (base / repl).resolve()))

            elif local == "rewriteURI":
                prefix = el.get("uriStartString", "")
                repl   = el.get("rewritePrefix", "")
                if prefix and repl:
                    self._rewrites.append((prefix, (base / repl).resolve()))

            elif local == "nextCatalog":
                next_rel = el.get("catalog", "")
                if next_rel:
                    next_path = (base / next_rel).resolve()
                    self._load_catalog(next_path, next_path.parent)

        # Längster Präfix zuerst (spezifischste Regel gewinnt)
        self._rewrites.sort(key=lambda t: -len(t[0]))

    # -- Öffentliche API -------------------------------------------------------

    def locate(self, url: str) -> Optional[Path]:
        """
        Übersetzt eine URL (http://, https:// oder relativer Pfad) in
        einen lokalen Dateipfad.  Gibt None zurück, wenn keine Regel passt.

        Suchreihenfolge:
          0. Bereits lokaler absoluter Pfad (lxml übergibt manchmal aufgelöste Pfade)
          1. Exakte <system>/<uri>-Einträge
          2. Präfix-Regeln (<rewriteSystem>/<rewriteURI>)
          3. Dateiname-only-Fallback in _fallback_dirs
        """
        if not url:
            return None

        # 0. Lokaler absoluter Pfad — direkt zurückgeben, kein Catalog-Lookup nötig
        #    (lxml ruft resolve() manchmal mit bereits aufgelösten file-Pfaden auf)
        if not url.startswith(("http://", "https://", "ftp://", "//")):
            try:
                p = Path(url)
                if p.is_absolute() and p.exists():
                    return p
            except (ValueError, OSError):
                pass

        # 1. Exakter Treffer
        if url in self._exact:
            p = self._exact[url]
            return p if p.exists() else None

        # 2. Präfix-Regeln
        for prefix, base_dir in self._rewrites:
            if url.startswith(prefix):
                suffix = url[len(prefix):]
                # Vollständiger Pfad (falls Unterverzeichnisse existieren)
                try:
                    candidate = base_dir / suffix
                    if candidate.exists():
                        return candidate
                except (ValueError, OSError):
                    pass
                # Flat-Fallback: nur Dateiname (häufigste Paketstruktur)
                try:
                    filename = Path(suffix).name
                    if filename:
                        flat = base_dir / filename
                        if flat.exists():
                            log.debug("Flat-Fallback: %s -> %s", url, flat)
                            return flat
                except (ValueError, OSError):
                    pass

        # 3. Dateiname-Fallback in konfigurierten Verzeichnissen.
        #    Schützt vor Dateinamen mit ':' (URN-Fragmente, Windows-Invalid).
        raw_filename = url.rstrip("/").rsplit("/", 1)[-1]
        if raw_filename.endswith(".xsd") and ":" not in raw_filename:
            for d in self._fallback_dirs:
                try:
                    candidate = d / raw_filename
                    if candidate.exists():
                        log.debug("Dir-Fallback: %s -> %s", url, candidate)
                        return candidate
                except (ValueError, OSError):
                    pass

        return None

    # -- lxml Resolver Interface -----------------------------------------------

    def resolve(self, url: str, id: str, context):
        """
        Wird von lxml aufgerufen, wenn eine externe Ressource geladen werden soll
        (DTD-Entities, XInclude, Schema-Validierung).
        """
        local = self.locate(url)
        if local:
            return self.resolve_filename(str(local), context)
        if url and url.startswith(("http://", "https://")):
            log.warning("Nicht aufgelöste externe URL: %s", url)
        return None  # lxml nutzt seinen Standard-Fallback


# --- Annotation-Extraktion ----------------------------------------------------

def extract_codelist_from_appinfo(
    node: etree._Element,
) -> tuple[str, str]:
    """
    Extrahiert (urn, version) aus einem xs:annotation/xs:appinfo-Block.
    Gibt ("", "") zurück, wenn keine XÖV-Codelisten-Annotation gefunden.

    Unterstützte Muster (in Reihenfolge absteigender Häufigkeit):

    Muster A — XÖV 3.x Standardformat (häufigster Fall in XAusländer 26.11):
      <xs:appinfo>
        <codeliste>
          <kennung>urn:de:xauslaender:codelist:...</kennung>
        </codeliste>
        <versionCodeliste>
          <version>4</version>
        </versionCodeliste>
      </xs:appinfo>

    Muster B — XInneres-Format (kennung in codeliste, ohne versionCodeliste):
      <xs:appinfo>
        <codeliste>
          <kennung>urn:xoev-de:xinneres:codeliste:geschlecht</kennung>
        </codeliste>
      </xs:appinfo>

    Muster C — listURI-Attribut (fixed=) in xs:restriction:
      <xs:attribute name="listURI" fixed="urn:xoev-de:..."/>

    Muster D — generischer Fallback: beliebiges Kind-Element mit URN-Text oder Attribut
    """
    XS = NS_XS
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

        # Version suchen: bevorzugt in <versionCodeliste><version>
        version = ""
        version_container = _find_child_by_local(appinfo, "versionCodeliste")
        if version_container is not None:
            ver_el = _find_child_by_local(version_container, "version")
            if ver_el is not None:
                version = (ver_el.text or "").strip()
        if not version:
            # Fallback: <version> direkt in <codeliste> oder in <appinfo>
            ver_el = (
                _find_child_by_local(codeliste_el, "version")
                or _find_child_by_local(appinfo, "version")
            )
            if ver_el is not None:
                version = (ver_el.text or "").strip()

        return urn, version

    # -- C: xs:attribute[@name='listURI'][@fixed='urn:...'] ------------------
    # (tritt in xs:restriction-Blöcken auf, z. B. in xinneres-geschlecht.xsd)
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
            parent = descendant.getparent()
            ver_el = _find_child_by_local(parent, "version") if parent is not None else None
            return text, (ver_el.text or "").strip() if ver_el is not None else ""

    return "", ""


def extract_display_names_from_appinfo(
    node: etree._Element,
) -> tuple[str, str]:
    """
    Extrahiert (name_short, name_long) aus xs:annotation/xs:appinfo/codeliste.
    Gibt ("", "") zurück, wenn keine Anzeigenamen gefunden.

    Unterstütztes Muster (XAusländer / XInneres):
      <xs:annotation>
        <xs:appinfo>
          <codeliste>
            <nameLang>Geschlechtsangaben in XInneres</nameLang>
            <nameKurz>XInneres Geschlecht</nameKurz>
            <nameTechnisch>geschlecht</nameTechnisch>
          </codeliste>
        </xs:appinfo>
      </xs:annotation>

    Rückgabe: (nameKurz, nameLang) → (display_name_short, display_name_long)
    """
    XS = NS_XS
    appinfo = node.find(f"{{{XS}}}annotation/{{{XS}}}appinfo")
    if appinfo is None:
        return "", ""

    for codeliste_el in appinfo.iter():
        if _local_name(codeliste_el) != "codeliste":
            continue
        lang_el  = _find_child_by_local(codeliste_el, "nameLang")
        kurz_el  = _find_child_by_local(codeliste_el, "nameKurz")
        name_long  = (lang_el.text  or "").strip() if lang_el  is not None else ""
        name_short = (kurz_el.text  or "").strip() if kurz_el  is not None else ""
        if name_long or name_short:
            return name_short, name_long

    return "", ""


# --- XSD-Parser ---------------------------------------------------------------

class XOVSchemaParser:
    """
    Parst XSD-Dateien des XÖV-Standards, folgt xs:import/xs:include-Ketten
    (via OASIS Catalog) und baut einen globalen Typ-Index auf.

    Ablauf:
      1. parse_directory(xsd_dir) — alle *.xsd einlesen + Typen indizieren
      2. resolve_codelist(type_ref) — Typreferenz -> (urn, version)
      3. extract_rules(primary_dir) — xs:element -> Regeleinträge
    """

    def __init__(self, catalog: OASISCatalogResolver) -> None:
        self._catalog    = catalog
        # Absoluter Pfad -> geparster Root-Knoten (None = Parse-Fehler)
        self._parsed:    dict[str, Optional[etree._Element]] = {}
        # Typname -> (Typ-Knoten, Quelldateiname) — first-wins
        self._type_idx:  dict[str, tuple[etree._Element, str]] = {}
        # Zyklusschutz während des Parsens
        self._parsing:   set[str] = set()

    # -- Parsing ---------------------------------------------------------------

    def _make_parser(self) -> etree.XMLParser:
        """
        Erstellt einen lxml-XMLParser mit registriertem Catalog-Resolver.
        resolve_entities=False schützt vor XXE (XML External Entity Injection).
        """
        p = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            recover=True,  # Parsing fortführen bei syntaktischen Kleinstfehlern
        )
        p.resolvers.add(self._catalog)
        return p

    def parse_file(self, path: Path) -> Optional[etree._Element]:
        """
        Parst eine XSD-Datei und folgt allen xs:import/xs:include-Referenzen.
        Zyklische Importe werden erkannt und übersprungen.
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

    # -- Import-Verfolgung -----------------------------------------------------

    def _follow_imports(self, root: etree._Element, current: Path) -> None:
        """
        Liest xs:import und xs:include aus root und parst die referenzierten
        XSD-Dateien rekursiv.  Auflösung über Catalog -> relative Pfad -> skip.
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
                    # NICHT versuchen, wenn loc eine absolute URL ist —
                    # Path() wirft OSError auf Windows bei "https://..."-Pfaden.
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

    # -- Typ-Index -------------------------------------------------------------

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

    # -- Codelisten-Auflösung --------------------------------------------------

    def resolve_codelist(
        self,
        type_ref: str,
        _visited: set[str] | None = None,
    ) -> tuple[str, str]:
        """
        Verfolgt eine Typreferenz durch den Typ-Index bis zu einer
        Codelisten-Annotation.  Gibt (urn, version) oder ("", "") zurück.

        Zyklusschutz: _visited speichert bereits besuchte Typnamen.
        Maximale Rekursionstiefe: implizit durch _visited begrenzt.
        """
        if _visited is None:
            _visited = set()

        # Namespace-Präfix entfernen: "xig:Code.Geschlecht" -> "Code.Geschlecht"
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

        # xs:restriction/@base -> Basistyp verfolgen
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

        # xs:complexContent -> eingebettete Element-Typen verfolgen
        for child_el in type_node.iter(f"{{{XS}}}element"):
            child_type = child_el.get("type", "").strip()
            if child_type:
                urn, ver = self.resolve_codelist(child_type, _visited)
                if urn:
                    return urn, ver

        return "", ""

    def resolve_display_names(
        self,
        type_ref: str,
        _visited: set[str] | None = None,
    ) -> tuple[str, str]:
        """
        Folgt der Typreferenz-Kette (wie resolve_codelist) und extrahiert
        Anzeigenamen aus xs:appinfo/codeliste/nameLang + nameKurz.

        Gibt (name_short, name_long) zurück oder ("", "") wenn nicht gefunden.
        """
        if _visited is None:
            _visited = set()

        local = type_ref.split(":")[-1] if ":" in type_ref else type_ref
        if not local or local in _visited:
            return "", ""
        _visited.add(local)

        if local not in self._type_idx:
            return "", ""

        type_node, _ = self._type_idx[local]

        name_short, name_long = extract_display_names_from_appinfo(type_node)
        if name_short or name_long:
            return name_short, name_long

        # Basistyp via xs:restriction/@base verfolgen
        XS = NS_XS
        restriction = type_node.find(f".//{{{XS}}}restriction")
        if restriction is not None:
            base = restriction.get("base", "").strip()
            if base:
                return self.resolve_display_names(base, _visited)

        return "", ""

    # -- Regel-Extraktion ------------------------------------------------------

    def extract_rules(self) -> dict[str, dict]:
        """
        Hauptextraktions-Pass: Für jedes geparste xs:element mit @name wird
        geprüft, ob es eine Codelisten-Bindung hat (direkt oder über Typen).

        Rückgabe: {element_name -> {target_column, xoev_urn, required_version,
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
                    continue  # ref= statt name= -> kein neuer Name

                # First-wins: Element bereits aus einer Prioritätsdatei bekannt
                if name in rules:
                    continue

                # type_ref muss vor dem URN-Check bekannt sein,
                # damit display_name-Auflösung dieselbe Referenz nutzen kann.
                type_ref = element.get("type", "").strip()

                # 1. Direkte Annotation am xs:element
                urn, ver = extract_codelist_from_appinfo(element)

                # 2. Annotation über Typreferenz (@type)
                if not urn and type_ref:
                    urn, ver = self.resolve_codelist(type_ref)

                if urn:
                    # Anzeigenamen: zuerst direkt am Element, sonst über den Typ
                    name_short, name_long = extract_display_names_from_appinfo(element)
                    if not name_short and not name_long and type_ref:
                        name_short, name_long = self.resolve_display_names(type_ref)

                    rules[name] = {
                        "target_column":      name,
                        "display_name_short": name_short,
                        "display_name_long":  name_long,
                        "xoev_urn":           urn,
                        "required_version":   ver,
                        "source_schema":      source_file,
                    }

        log.info("Extrahierte Codelisten-Regeln: %d", len(rules))
        return dict(sorted(rules.items()))


# --- Hilfsfunktionen ----------------------------------------------------------

def _local_name(el: etree._Element) -> str:
    """'{http://...}localname' -> 'localname' (namespace-agnostisch)."""
    tag = el.tag
    return tag.split("}")[-1] if isinstance(tag, str) and "}" in tag else tag


def _find_child_by_local(parent: etree._Element, local: str) -> Optional[etree._Element]:
    """Findet das erste Kind-Element mit passendem Local-Name (jeder Namespace)."""
    for child in parent:
        if _local_name(child) == local:
            return child
    return None


def _is_xoev_urn(value: str) -> bool:
    """Gibt True zurück, wenn value ein bekanntes XÖV-URN-Präfix hat."""
    return any(value.startswith(p) for p in _XOEV_URN_PREFIXES)


# --- Genericode Codelisten-Parser ---------------------------------------------

def _find_recommended_key_column(root: etree._Element) -> str:
    """
    Ermittelt die Id der empfohlenen Code-Spalte aus dem ColumnSet.

    Priorisierung:
      1. Key mit Annotation <xoev-cl-3:empfohleneCodeSpalte/> (XInneres-Format)
         oder <xoev-cl-4:recommendedKeyColumn/>  (XAusländer-Format)
      2. Erster Key im ColumnSet als Fallback
    """
    recommended_tags = {
        f"{{{NS_CL3}}}empfohleneCodeSpalte",
        f"{{{NS_CL4}}}recommendedKeyColumn",
    }
    for key in root.iter("Key"):
        # Suche empfohlene-Code-Spalte-Annotation innerhalb dieses Keys
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


def parse_genericode_codes(path: Path) -> list[str]:
    """
    Extrahiert alle Code-Werte aus einer Genericode-XML-Datei (OASIS Genericode 1.0).

    Struktur der XÖV-Codelisten-Dateien:
      <gc:CodeList>
        <ColumnSet>
          <Key>                         <- empfohlene Code-Spalte ermitteln
            <ColumnRef Ref="CodeId"/>
          </Key>
        </ColumnSet>
        <SimpleCodeList>
          <Row>
            <Value ColumnRef="CodeId">
              <SimpleValue>01</SimpleValue>   <- dieser Wert wird extrahiert
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
        # Absolute Notfall-Fallback: Id des ersten <Column>-Elements
        first_col = root.find(".//Column")
        code_col_id = first_col.get("Id", "") if first_col is not None else ""

    if not code_col_id:
        log.warning("Keine Code-Spalte gefunden in: %s", path.name)
        return []

    codes: list[str] = []
    for row in root.iter("Row"):
        for val in row:  # direkte Kinder von Row
            if val.get("ColumnRef") == code_col_id:
                sv = val.find("SimpleValue")
                if sv is not None and sv.text:
                    text = sv.text.strip()
                    if text:
                        codes.append(text)
                break  # pro Row nur einen Treffer

    return codes


class GenericodeIndex:
    """
    Scannt alle *.xml-Codelisten-Dateien in den angegebenen Verzeichnissen,
    liest jeweils nur <Identification><CanonicalUri> via iterparse (ohne vollen DOM),
    und baut einen schnellen URN -> Path Lookup-Index auf.

    Unterstützt mehrere Verzeichnisse gleichzeitig (XAusländer + XInneres).
    First-wins: bei doppelter URN gewinnt die zuerst gefundene Datei.
    """

    def __init__(self, *codelisten_dirs: Path) -> None:
        self._index:  dict[str, Path] = {}
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
        """Liest nur CanonicalUri via iterparse — speichereffizient auch bei grossen Dateien."""
        for _, el in etree.iterparse(str(path), events=("end",), tag="CanonicalUri"):
            return (el.text or "").strip()
        return ""

    def locate(self, urn: str) -> Optional[Path]:
        """Gibt den Dateipfad für die gegebene URN zurück, oder None."""
        return self._index.get(urn)


def enrich_rules_with_codes(
    rules: dict[str, dict],
    index: GenericodeIndex,
) -> tuple[dict[str, dict], int, int]:
    """
    Anreicherungsschicht: Ergänzt jeden Regeleintrag um 'allowed_codes'.

    - URN in GenericodeIndex vorhanden  -> Codes parsen und einbetten
    - URN nicht gefunden                -> WARNING loggen, allowed_codes = []
    - URN leer (kein Codelisten-Feld)   -> allowed_codes = [] (kein Log-Rauschen)

    Gibt zurück: (angereicherte_regeln, anzahl_gefunden, anzahl_nicht_gefunden)
    """
    found = 0
    not_found = 0
    enriched: dict[str, dict] = {}

    for name, rule in rules.items():
        urn  = rule.get("xoev_urn", "")
        path = index.locate(urn) if urn else None

        if path:
            codes = parse_genericode_codes(path)
            found += 1
            log.debug(
                "  [OK] %-55s %3d Codes  [%s]",
                urn, len(codes), path.name,
            )
        else:
            codes = []
            not_found += 1
            if urn:
                log.warning("Codeliste nicht auf Disk: %s", urn)

        enriched[name] = {**rule, "allowed_codes": codes}

    return enriched, found, not_found


# --- CLI / Hauptprogramm ------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="XÖV XAusländer Schema -> rules_xauslaender.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Aufruf aus xrepository/: python parse_xoev_rules.py",
    )
    ap.add_argument(
        "--catalog",
        default="catalog.xml",
        metavar="PATH",
        help="OASIS XML Catalog (Standard: catalog.xml)",
    )
    ap.add_argument(
        "--xauslaender-xsd",
        default="xöv-registry/xauslaender/26.11/xsd",
        metavar="DIR",
        help="Verzeichnis mit XAusländer-XSD-Dateien",
    )
    ap.add_argument(
        "--xinneres-xsd",
        default="xöv-registry/xinneres/26.11/xsd",
        metavar="DIR",
        help="Verzeichnis mit XInneres-XSD-Dateien (Fallback-Dir für Katalog)",
    )
    ap.add_argument(
        "--output",
        default="rules_xauslaender.json",
        metavar="FILE",
        help="Ausgabedatei (Standard: rules_xauslaender.json)",
    )
    ap.add_argument(
        "--xauslaender-codelisten",
        default="xöv-registry/xauslaender/26.11/codelisten",
        metavar="DIR",
        help="Verzeichnis mit XAusländer Genericode-Codelisten (Standard: xöv-registry/xauslaender/26.11/codelisten)",
    )
    ap.add_argument(
        "--xinneres-codelisten",
        default="xöv-registry/xinneres/26.11/codelisten",
        metavar="DIR",
        help="Verzeichnis mit XInneres Genericode-Codelisten (Standard: xöv-registry/xinneres/26.11/codelisten)",
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="DEBUG-Logging aktivieren")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)

    base         = Path.cwd()
    catalog_path = base / "xrepository" / args.catalog
    xa_xsd_dir   = base / "xrepository" / args.xauslaender_xsd
    xi_xsd_dir   = base / "xrepository" / args.xinneres_xsd
    xa_cl_dir    = base / "xrepository" / args.xauslaender_codelisten
    xi_cl_dir    = base / "xrepository" / args.xinneres_codelisten
    output_path  = base / "xrepository" / args.output

    # -- Voraussetzungen prüfen ------------------------------------------------
    missing = [(lbl, p) for lbl, p in [
        ("catalog.xml",         catalog_path),
        ("XAusländer XSD-Dir",  xa_xsd_dir),
    ] if not p.exists()]
    if missing:
        for lbl, p in missing:
            log.error("Nicht gefunden: %s: %s", lbl, p)
        sys.exit(1)

    fallback_dirs = [xi_xsd_dir] if xi_xsd_dir.is_dir() else []
    if not fallback_dirs:
        log.warning(
            "XInneres XSD-Verzeichnis nicht gefunden (%s) — "
            "Cross-Schema-Typen (z. B. Geschlecht) koennen nicht aufgeloest werden.",
            xi_xsd_dir,
        )

    # -- Parser initialisieren -------------------------------------------------
    catalog = OASISCatalogResolver(catalog_path, fallback_dirs)
    parser  = XOVSchemaParser(catalog)

    # -- Phase 1: XAusländer-Schemata parsen (loest XInneres-Imports aus) -----
    log.info("=== Phase 1: XAuslaender-Schemata parsen ===")
    parser.parse_directory(xa_xsd_dir)

    # -- Phase 2: XInneres vorsorglich einlesen (fuer vollstaendigen Typ-Index) -
    if fallback_dirs:
        log.info("=== Phase 2: XInneres-Schemata nachindizieren ===")
        parser.parse_directory(xi_xsd_dir)

    # -- Phase 3: Regeln aus XSD-Annotationen extrahieren ---------------------
    log.info("=== Phase 3: Codelisten-Regeln extrahieren ===")
    rules = parser.extract_rules()

    # -- Phase 4: Genericode-Index aufbauen (URN -> XML-Pfad) -----------------
    log.info("=== Phase 4: Genericode-Codelisten indizieren ===")
    gc_index = GenericodeIndex(xa_cl_dir, xi_cl_dir)

    # -- Phase 5: Regeln mit echten Codes anreichern ---------------------------
    log.info("=== Phase 5: Codes aus XML-Codelisten einbetten ===")
    enriched_rules, found_count, not_found_count = enrich_rules_with_codes(rules, gc_index)

    # -- Phase 6: Monolithisches JSON-Profil schreiben -------------------------
    monolith = {
        "schema_id":     "xauslaender_compiled",
        "schema_name":   "XAuslaender Vollpruefung Profile",
        "version":       "26.11",
        "xoev_standard": "XAuslaender",
        "description": (
            "Monolithisches Validierungsprofil, automatisch kompiliert aus "
            "XSD-Annotationen und Genericode-Codelisten des XAuslaender-Standards v26.11. "
            f"Enthalt {len(enriched_rules)} Felder, davon {found_count} mit eingebetteten Codes."
        ),
        "fields": enriched_rules,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(monolith, f, ensure_ascii=False, indent=2)

    # -- Zusammenfassung -------------------------------------------------------
    ok_files    = sum(1 for v in parser._parsed.values() if v is not None)
    total_files = len(parser._parsed)
    total_types = len(parser._type_idx)
    with_codes  = sum(1 for r in enriched_rules.values() if r.get("allowed_codes"))

    sep = "=" * 60
    print(f"\n{sep}")
    print("  XOEv Rules Parser - Monolithisches Profil kompiliert")
    print(sep)
    print(f"  XSD-Dateien verarbeitet      : {ok_files} / {total_files}")
    print(f"  Typen im Index               : {total_types}")
    print(f"  Codelisten-Felder gefunden   : {len(rules)}")
    print(f"  Genericode-Dateien gescannt  : {gc_index.total_scanned}")
    print(f"  Genericode-URNs indiziert    : {gc_index.total_indexed}")
    print(f"  Codes erfolgreich eingebettet: {found_count}  ({with_codes} Felder mit Codes)")
    print(f"  Codelisten nicht gefunden    : {not_found_count}")
    print(f"  Ausgabedatei                 : {output_path.relative_to(base)}")
    print("-" * 60)
    if enriched_rules:
        print("  Beispiele (erste 6 mit Codes):")
        count = 0
        for name, rule in enriched_rules.items():
            codes = rule.get("allowed_codes", [])
            if codes:
                preview = str(codes[:4])[:-1] + ("..." if len(codes) > 4 else "]")
                print(f"    {name:<35} {len(codes):>3} Codes  {preview}")
                count += 1
                if count >= 6:
                    break
    else:
        print("  WARNUNG: Keine Regeln gefunden!")
        print("  -> Pruefen Sie catalog.xml und die XSD-Verzeichnisse.")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
