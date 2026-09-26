#!/usr/bin/env python3
"""
Добавляет known_fields в скомпилированные монолиты.

known_fields = плоский список ВСЕХ xs:element name= из XSD-файлов стандарта,
нормализованных к lowercase. Используется validate_headers() для различения:
  - Поле в fields     → валидируем по codelist
  - Поле в known_fields → признаём как легитимное, значение не валидируем
  - Нигде нет         → amber NICHT_IM_PROFIL (реально не в XÖV-схеме)

Запуск:  cd backend && python !/add_known_fields.py
"""
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS_XS  = "http://www.w3.org/2001/XMLSchema"
BASE   = Path(__file__).parent.parent  # backend/

TARGETS = [
    {
        "xsd_dir": BASE / "xrepository/xoev-registry/de/osci/xauslaender/26.11/xsd",
        "monolith": BASE / "rules/xauslaender_26.11_compiled.json",
        "label":   "XAusländer 26.11",
    },
    {
        # XMeld — попробуем найти директорию
        "xsd_dir": BASE / "xrepository/xoev-registry/de/osci/xmeld/26.11/xsd",
        "monolith": BASE / "rules/xmeld_26.11_compiled.json",
        "label":   "XMeld 26.11",
    },
]


def extract_element_names(xsd_dir: Path) -> list[str]:
    """Читает все *.xsd в директории и собирает уникальные имена xs:element."""
    names: set[str] = set()
    if not xsd_dir.exists():
        return []
    for xsd_file in sorted(xsd_dir.glob("*.xsd")):
        try:
            root = ET.parse(xsd_file).getroot()
        except ET.ParseError as e:
            print(f"  [WARN] ParseError {xsd_file.name}: {e}")
            continue
        for el in root.iter(f"{{{NS_XS}}}element"):
            name = el.get("name", "").strip()
            if name:
                names.add(name.lower())
    return sorted(names)


def process(cfg: dict) -> None:
    label    = cfg["label"]
    xsd_dir  = cfg["xsd_dir"]
    monolith = cfg["monolith"]

    print(f"\n{'─'*55}")
    print(f"  {label}")
    print(f"  XSD:      {xsd_dir}")
    print(f"  Monolith: {monolith}")

    if not monolith.exists():
        print(f"  [SKIP] Monolith-Datei nicht gefunden.")
        return

    if not xsd_dir.exists():
        print(f"  [SKIP] XSD-Verzeichnis nicht gefunden.")
        return

    # Alle Elementnamen aus XSD extrahieren
    names = extract_element_names(xsd_dir)
    print(f"  Gefunden: {len(names)} XSD-Elementnamen")

    # Monolith laden
    with open(monolith, encoding="utf-8") as f:
        schema = json.load(f)

    existing_fields: int
    fld = schema.get("fields", {})
    if isinstance(fld, dict):
        existing_fields = len(fld)
        existing_keys   = {k.lower() for k in fld}
    elif isinstance(fld, list):
        existing_fields = len(fld)
        existing_keys   = {
            (r.get("name") or r.get("target_column") or "").lower()
            for r in fld if isinstance(r, dict)
        }
    else:
        existing_fields = 0
        existing_keys   = set()

    # Nur Felder die NICHT bereits im codelist-Dict sind
    non_codelist = [n for n in names if n not in existing_keys]

    schema["known_fields"] = names  # komplette Liste — engine prüft beide

    with open(monolith, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    print(f"  Codelist-Felder:        {existing_fields}")
    print(f"  known_fields gesamt:    {len(names)}")
    print(f"  Davon nur bekannt:      {len(non_codelist)}")
    print(f"  Monolith aktualisiert ✓")


def main() -> None:
    print("=" * 55)
    print("  known_fields Updater")
    print("=" * 55)
    for cfg in TARGETS:
        process(cfg)
    print(f"\n{'='*55}")
    print("  Fertig.")


if __name__ == "__main__":
    main()
