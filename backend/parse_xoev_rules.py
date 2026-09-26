#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_xoev_rules.py — VERALTET / DEPRECATED
============================================
Dieser Einstiegspunkt wurde refaktoriert und leitet automatisch weiter.

Neuer Einstiegspunkt:
    python import/parse_xoev_rules.py [--verbose] [--registry DIR] [--output-dir DIR]

Aktive Logik jetzt in:
    backend/import/parser/resolver.py
    backend/import/parser/genericode.py
    backend/import/parser/xsd_parser.py
    backend/import/parser/pipeline.py
    backend/import/parse_xoev_rules.py
"""
import importlib.util
import sys
from pathlib import Path

_entry = Path(__file__).resolve().parent / "import" / "parse_xoev_rules.py"
_spec  = importlib.util.spec_from_file_location("_xoev_import_entry", _entry)
_mod   = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.exit(_mod.main() or 0)
