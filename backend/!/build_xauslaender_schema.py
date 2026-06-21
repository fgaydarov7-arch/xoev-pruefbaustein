#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
XÖV/XAusländer Schema Builder
==============================
Парсит XSD-файлы стандарта XAusländer и Genericode XML-справочники,
автоматически генерирует schema.json для валидатора таблиц.

Запуск:
    cd backend
    python build_xauslaender_schema.py

Выходной файл:
    backend/rules/xauslaender_azr_26_11.json
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ─── Пути ────────────────────────────────────────────────────────────────────

BASE_DIR      = Path(__file__).parent
SCHEMATA_DIR  = BASE_DIR / "shemas" / "xauslaender" / "schemata"
CODELISTE_DIR = BASE_DIR / "shemas" / "xauslaender" / "codeliste"
OUTPUT_FILE   = BASE_DIR / "rules" / "xauslaender_azr_26_11.json"

# ─── XML Namespaces ───────────────────────────────────────────────────────────

NS_XS      = "http://www.w3.org/2001/XMLSchema"
NS_GC      = "http://docs.oasis-open.org/codelist/ns/genericode/1.0/"
NS_XOEV_CL = "http://xoev.de/schemata/genericode/4"

NS = {
    "xs":       NS_XS,
    "gc":       NS_GC,
    "xoev-cl-4": NS_XOEV_CL,
}

# ─── Типы XSD → тип поля в JSON ──────────────────────────────────────────────

# Подстроки в имени XSD-типа, сигнализирующие о дате
DATE_TYPE_HINTS = {"datum", "date", "monat", "tagesdatum", "jahresdatum"}

# Коделисты для типов из xs:import внешних пространств имён (не в локальных XSD).
# Code.Geschlecht → xig-Namespace (http://www.osci.de/xinneres/geschlecht/1).
# Значения согласно XInnerens 2.x / PStG § 22 Abs. 3 und SBGG 2024.
FALLBACK_CODELISTS: dict[str, list[str]] = {
    "Code.Geschlecht": ["1", "2", "3", "4"],
    # 1=männlich  2=weiblich  3=divers  4=unbestimmt
}

# XSD primitive types → наш тип
XSD_TYPE_MAP = {
    "xs:date":        "date",
    "xs:gYearMonth":  "date",
    "xs:dateTime":    "date",
    "xs:boolean":     "boolean",
    "xs:integer":     "number",
    "xs:decimal":     "number",
    "xs:positiveInteger": "number",
    "xs:nonNegativeInteger": "number",
}

# ─── Немецкие подсказки по типу ошибки ───────────────────────────────────────

def build_fix_suggestion(
    name: str,
    field_type: str,
    codelist: list[str],
    description: str,
) -> str:
    if field_type == "date":
        return (
            f"Bitte ein gültiges Datum für '{name}' angeben. "
            "Format: TT.MM.JJJJ (z. B. 15.04.1990) oder JJJJ-MM-TT."
        )
    if field_type == "boolean":
        return f"Erlaubter Wert für '{name}': 'true' oder 'false'."
    if field_type == "number":
        return f"Bitte eine gültige Zahl für '{name}' eingeben."
    if codelist:
        if len(codelist) <= 8:
            return (
                f"Erlaubte Werte für '{name}': "
                + ", ".join(f"'{c}'" for c in codelist)
                + "."
            )
        preview = ", ".join(f"'{c}'" for c in codelist[:4])
        return (
            f"Bitte einen gültigen Code aus der offiziellen XÖV-Codeliste "
            f"für '{name}' angeben (z. B. {preview} …). "
            f"Insgesamt {len(codelist)} erlaubte Werte."
        )
    # Generic fallback
    hint = description[:120].rstrip() if description else ""
    if hint:
        return f"Ungültiger Wert für '{name}'. Hinweis: {hint}"
    return f"Bitte einen gültigen Wert für das Pflichtfeld '{name}' angeben."


# ─── Hauptklasse ──────────────────────────────────────────────────────────────

class XauslaenderSchemaBuilder:
    """
    Schritt 1: parse_codes_xsd()      → self.code_registry
    Schritt 2: parse_all_codelists()  → self.codelist_registry
    Schritt 3: parse_all_schemata()   → self.element_registry
    Schritt 4: generate_schema()      → list[dict]  → JSON
    """

    def __init__(self, schemata_dir: Path, codeliste_dir: Path) -> None:
        self.schemata_dir  = schemata_dir
        self.codeliste_dir = codeliste_dir

        # type_name → {"kennung": str, "name_lang": str,
        #               "beschreibung": str, "enumerations": list[str]}
        self.code_registry: dict[str, dict] = {}

        # canonical_uri → list[str] of code values (aus Genericode XML)
        self.codelist_registry: dict[str, list[str]] = {}

        # canonical_uri → human-readable description
        self.codelist_descriptions: dict[str, str] = {}

        # element_name_lower → {"xsd_type": str, "required": bool,
        #                        "description": str, "source_file": str}
        self.element_registry: dict[str, dict] = {}

    # ── Шаг 1: Парсинг codes.xsd ─────────────────────────────────────────────

    def parse_codes_xsd(self) -> None:
        """
        Читает xauslaender-codes.xsd и строит self.code_registry.

        Два паттерна:
          A) Встроенные xs:enumeration → коды прямо в XSD
          B) xs:token + listURI attr   → коды во внешнем Genericode XML
        """
        path = self.schemata_dir / "xauslaender-codes.xsd"
        tree = ET.parse(path)
        root = tree.getroot()

        for ct in root.findall(f"{{{NS_XS}}}complexType"):
            type_name = ct.get("name", "")
            if not type_name.startswith("Code."):
                continue

            # Метаданные из <xs:appinfo><codeliste>
            kennung     = ""
            name_lang   = ""
            beschreibung = ""
            codeliste_el = ct.find(".//codeliste")  # no namespace (inside appinfo)
            if codeliste_el is not None:
                kennung      = _text(codeliste_el, "kennung")
                name_lang    = _text(codeliste_el, "nameLang")
                beschreibung = _text(codeliste_el, "beschreibung")

            # Встроенные коды (xs:enumeration)
            enumerations = [
                e.get("value", "")
                for e in ct.findall(f".//{{{NS_XS}}}enumeration")
                if e.get("value")
            ]

            self.code_registry[type_name] = {
                "kennung":      kennung,
                "name_lang":    name_lang,
                "beschreibung": beschreibung,
                "enumerations": enumerations,
            }

        print(f"  [codes.xsd] Gefunden: {len(self.code_registry)} Code-Typen")

    # ── Шаг 2: Парсинг всех Genericode XML ───────────────────────────────────

    def parse_all_codelists(self) -> None:
        """
        Indexiert alle *.xml Genericode-Dateien nach CanonicalUri.
        Bestimmt die empfohlene Key-Spalte und extrahiert alle Codewerte.
        """
        xml_files = sorted(self.codeliste_dir.glob("*.xml"))
        ok, skipped = 0, 0
        for xml_file in xml_files:
            try:
                result = self._parse_single_codelist(xml_file)
                if result:
                    ok += 1
                else:
                    skipped += 1
            except Exception as exc:
                print(f"  [WARN] {xml_file.name}: {exc}")
                skipped += 1
        print(f"  [codeliste] Indiziert: {ok} Codelisten, {skipped} übersprungen")

    def _parse_single_codelist(self, path: Path) -> bool:
        """
        Parst eine einzelne Genericode XML.
        Gibt True zurück, wenn Codes erfolgreich extrahiert wurden.

        WICHTIG: ElementTree-Gotcha — ein <Element> ohne Kinder ist bool-falsy.
        Daher NIEMALS `el = a.find(...) or b.find(...)` nutzen,
        stets `el = a.find(...); if el is None: el = b.find(...)`.
        """
        tree = ET.parse(path)
        root = tree.getroot()

        # CanonicalUri — Schlüssel für die Zuordnung
        canonical_uri = self._gc_text(root, "Identification/CanonicalUri")
        if not canonical_uri:
            return False

        # Ermittle empfohlene Key-Spalte
        key_col_id = self._find_key_column_id(root)
        if not key_col_id:
            return False

        # Extrahiere Codewerte
        codes: list[str] = []
        simple_code_list = root.find("SimpleCodeList")
        if simple_code_list is None:
            simple_code_list = root.find(f"{{{NS_GC}}}SimpleCodeList")
        if simple_code_list is None:
            return False

        rows = simple_code_list.findall("Row")
        if not rows:
            rows = simple_code_list.findall(f"{{{NS_GC}}}Row")

        for row in rows:
            values = row.findall("Value")
            if not values:
                values = row.findall(f"{{{NS_GC}}}Value")
            for value in values:
                if value.get("ColumnRef") == key_col_id:
                    # ← Kein `or` hier! Element ohne Kinder ist bool-falsy in ET.
                    sv = value.find("SimpleValue")
                    if sv is None:
                        sv = value.find(f"{{{NS_GC}}}SimpleValue")
                    if sv is not None and sv.text and sv.text.strip():
                        codes.append(sv.text.strip())

        if not codes:
            return False

        # Kurzbeschreibung
        short_name = (
            self._gc_ns_text(root, f"Annotation/Description/{{{NS_XOEV_CL}}}shortName")
            or self._gc_text(root, "Identification/ShortName")
            or path.stem
        )

        self.codelist_registry[canonical_uri]    = codes
        self.codelist_descriptions[canonical_uri] = short_name
        return True

    def _find_key_column_id(self, root) -> str:
        """
        Bestimmt die empfohlene Key-Spalte aus dem ColumnSet.

        Priorität:
          1. Key mit <xoev-cl-4:recommendedKeyColumn/> Annotation
          2. Erste Key-Element (Fallback)
        """
        col_set = root.find("ColumnSet") or root.find(f"{{{NS_GC}}}ColumnSet")
        if col_set is None:
            return ""

        keys = col_set.findall("Key") or col_set.findall(f"{{{NS_GC}}}Key")
        if not keys:
            return ""

        # Suche nach recommendedKeyColumn
        for key in keys:
            ann_path = "Annotation/AppInfo/{%s}recommendedKeyColumn" % NS_XOEV_CL
            if key.find(ann_path) is not None:
                # ← Kein `or` — ColumnRef hat keine Kinder, wäre bool-falsy
                col_ref = key.find("ColumnRef")
                if col_ref is None:
                    col_ref = key.find(f"{{{NS_GC}}}ColumnRef")
                if col_ref is not None:
                    return col_ref.get("Ref", "")

        # Fallback: erster Key
        col_ref = keys[0].find("ColumnRef")
        if col_ref is None:
            col_ref = keys[0].find(f"{{{NS_GC}}}ColumnRef")
        return col_ref.get("Ref", "") if col_ref is not None else ""

    # ── Шаг 3: Парсинг XSD файлов на элементы ────────────────────────────────

    def parse_all_schemata(self) -> None:
        """
        Extrahiert xs:element Definitionen aus Baukasten-XSD-Dateien.
        Wertet 'type'-Attribut und minOccurs aus.
        """
        # Priorisierte Dateien: Baukasten zuerst (definieren Kerndatentypen)
        priority_files = [
            "xauslaender-baukasten.xsd",
            "xauslaender-basistypen.xsd",
            "xauslaender-allgemeine-datentypen.xsd",
        ]
        # Danach Nachrichten-XSDs für vollständige Abdeckung
        all_xsd = sorted(self.schemata_dir.glob("*.xsd"))
        other_files = [
            f for f in all_xsd
            if f.name not in priority_files and f.name != "xinneres.xauslaender.xsd"
        ]

        for name in priority_files:
            path = self.schemata_dir / name
            if path.exists():
                self._extract_elements(path)

        for path in other_files:
            self._extract_elements(path)

        print(f"  [schemata] Gefunden: {len(self.element_registry)} einzigartige Elemente")

    def _extract_elements(self, path: Path) -> None:
        """
        Liest alle <xs:element name="..." type="..."> aus einer XSD-Datei.
        Elemente ohne 'type'-Attribut (anonym) werden übersprungen.
        Bereits bekannte Elementnamen werden NICHT überschrieben (first-wins).
        """
        try:
            tree = ET.parse(path)
        except ET.ParseError as e:
            print(f"  [WARN] ParseError in {path.name}: {e}")
            return

        root = tree.getroot()

        for el in root.iter(f"{{{NS_XS}}}element"):
            name     = el.get("name", "").strip()
            type_ref = el.get("type", "").strip()
            if not name or not type_ref:
                continue

            name_lower = name.lower()
            # First-wins: Baukasten-Definitionen haben Vorrang
            if name_lower in self.element_registry:
                continue

            min_occurs = el.get("minOccurs", "1")
            required   = (min_occurs != "0")

            # Dokumentation aus xs:documentation
            description = ""
            doc_el = el.find(f".//{{{NS_XS}}}documentation")
            if doc_el is not None and doc_el.text:
                description = doc_el.text.strip()[:300]

            # Namespace-Präfix entfernen (xauslaender:Code.X → Code.X)
            clean_type = type_ref.split(":")[-1] if ":" in type_ref else type_ref

            self.element_registry[name_lower] = {
                "original_name": name,
                "xsd_type":      clean_type,
                "required":      required,
                "description":   description,
                "source_file":   path.name,
            }

    # ── Шаг 4: Генерация JSON-схемы ──────────────────────────────────────────

    def generate_schema(self) -> list[dict]:
        """
        Für jedes registrierte Element:
          1. Bestimme type (string/date/number/boolean)
          2. Suche Codeliste via code_registry + codelist_registry
          3. Erstelle fix_suggestion auf Deutsch
        """
        fields: list[dict] = []
        stats = defaultdict(int)

        for name_lower, meta in sorted(self.element_registry.items()):
            xsd_type    = meta["xsd_type"]
            required    = meta["required"]
            description = meta["description"]
            orig_name   = meta["original_name"]

            # ── Typ bestimmen ─────────────────────────────────────────────
            field_type = self._resolve_type(xsd_type)

            # ── Codeliste auflösen ────────────────────────────────────────
            codelist: list[str] = []
            codelist_name = ""

            if xsd_type in self.code_registry:
                reg = self.code_registry[xsd_type]
                kennung = reg["kennung"]

                if reg["enumerations"]:
                    # Koalierte Codes direkt aus XSD (Enumeration)
                    codelist = reg["enumerations"]
                    codelist_name = reg["name_lang"] or xsd_type
                    stats["embedded_enum"] += 1
                elif kennung and kennung in self.codelist_registry:
                    # Codes aus externem Genericode XML
                    codelist = self.codelist_registry[kennung]
                    codelist_name = self.codelist_descriptions.get(kennung, "")
                    stats["external_codelist"] += 1
                else:
                    # Code-Typ, aber keine Codeliste gefunden
                    stats["code_no_list"] += 1
            elif xsd_type in FALLBACK_CODELISTS:
                # Typ aus xs:import-Namespace (kein lokales XSD) → statischer Fallback
                codelist = FALLBACK_CODELISTS[xsd_type]
                codelist_name = xsd_type
                stats["fallback_codelist"] += 1
            else:
                stats["plain_type"] += 1

            # ── JSON-Felddefinition bauen ─────────────────────────────────
            field: dict = {
                "name":         name_lower,
                "display_name": orig_name,
                "type":         field_type,
                "required":     required,
            }

            if codelist:
                field["codelist"] = codelist

            if codelist_name:
                field["codelist_name"] = codelist_name

            field["fix_suggestion"] = build_fix_suggestion(
                name_lower, field_type, codelist, description
            )

            if description:
                field["description"] = description

            fields.append(field)

        print(
            f"  [generate] Felder: {len(fields)} total | "
            f"enum={stats['embedded_enum']} ext={stats['external_codelist']} "
            f"fallback={stats['fallback_codelist']} "
            f"no_list={stats['code_no_list']} plain={stats['plain_type']}"
        )
        return fields

    def _resolve_type(self, xsd_type: str) -> str:
        """Leitet den vereinfachten Datentyp aus dem XSD-Typ-Namen ab."""
        lower = xsd_type.lower()

        # Direkte XSD-Primitive
        for primitive, mapped in XSD_TYPE_MAP.items():
            if primitive.split(":")[-1].lower() == lower:
                return mapped

        # Datums-Heuristik nach Typname
        for hint in DATE_TYPE_HINTS:
            if hint in lower:
                return "date"

        # Code-Typen → immer string (Codeliste wird separat gesetzt)
        if xsd_type.startswith("Code."):
            return "string"

        # DIN 91379 Zeichensatz-Typen → string
        if lower.startswith("datatype"):
            return "string"

        return "string"

    # ── Hilfsmethoden ────────────────────────────────────────────────────────

    @staticmethod
    def _gc_text(root, xpath: str) -> str:
        """Findet Text in Genericode XML (ohne Namespace)."""
        el = root.find(xpath)
        return (el.text or "").strip() if el is not None else ""

    @staticmethod
    def _gc_ns_text(root, xpath: str) -> str:
        """Findet Text in Genericode XML (mit Namespace)."""
        el = root.find(xpath)
        return (el.text or "").strip() if el is not None else ""


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _text(parent, tag: str) -> str:
    """Liest Text eines direkten Kind-Elements (kein Namespace)."""
    el = parent.find(tag)
    return (el.text or "").strip() if el is not None else ""


def camel_to_words(name: str) -> str:
    """'staatsangehoerigkeit' → 'Staatsangehoerigkeit' (simple capitalize)."""
    return name[0].upper() + name[1:] if name else name


# ─── Schema-Metadaten ────────────────────────────────────────────────────────

SCHEMA_META = {
    "schema_id":    "xauslaender_azr_26_11",
    "schema_name":  "XAusländer AZR (Version 26.11)",
    "version":      "26.11",
    "xoev_standard": "XAusländer",
    "description": (
        "Automatisch generiertes Validierungsschema aus den XSD-Dateien und "
        "Genericode-Codelisten des XAusländer-Standards v26.11 (OSCI/KoSIT). "
        "Enthält alle im Baukasten und in den Nachrichtentypen definierten Felder "
        "mit ihren offiziellen Codelisten-Einschränkungen."
    ),
}


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("XÖV/XAusländer Schema Builder v1.0")
    print(f"Schemata: {SCHEMATA_DIR}")
    print(f"Codeliste: {CODELISTE_DIR}")
    print(f"Ausgabe:  {OUTPUT_FILE}")
    print("=" * 60)

    # Verzeichnisse prüfen
    for d in (SCHEMATA_DIR, CODELISTE_DIR):
        if not d.exists():
            print(f"FEHLER: Verzeichnis nicht gefunden: {d}", file=sys.stderr)
            sys.exit(1)

    builder = XauslaenderSchemaBuilder(SCHEMATA_DIR, CODELISTE_DIR)

    print("\nSchritt 1: Code-Typen aus xauslaender-codes.xsd einlesen …")
    builder.parse_codes_xsd()

    print("\nSchritt 2: Genericode-Codelisten indexieren …")
    builder.parse_all_codelists()

    print("\nSchritt 3: Elemente aus Schemata extrahieren …")
    builder.parse_all_schemata()

    print("\nSchritt 4: JSON-Schema generieren …")
    fields = builder.generate_schema()

    # Gesamtschema zusammenbauen
    schema = {**SCHEMA_META, "fields": fields}

    # Ausgabe
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    # Statistik
    codelist_fields = sum(1 for fd in fields if "codelist" in fd)
    date_fields     = sum(1 for fd in fields if fd["type"] == "date")
    required_fields = sum(1 for fd in fields if fd["required"])

    print("\n" + "=" * 60)
    print("Fertig!")
    print(f"  Felder gesamt:     {len(fields)}")
    print(f"  Pflichtfelder:     {required_fields}")
    print(f"  Mit Codeliste:     {codelist_fields}")
    print(f"  Datumsfelder:      {date_fields}")
    print(f"  Ausgabedatei:      {OUTPUT_FILE}")
    print("=" * 60)

    # Vorschau der ersten 5 Felder
    print("\nVorschau (erste 5 Felder):")
    for fd in fields[:5]:
        cl_info = f"  codelist[{len(fd['codelist'])}]" if "codelist" in fd else ""
        print(f"  {fd['name']:<35} type={fd['type']:<8} required={fd['required']}{cl_info}")


if __name__ == "__main__":
    main()
