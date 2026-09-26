#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_xoev_rules.py — XÖV Profil-Compiler (CLI-Einstiegspunkt)

Liest backend/import/config.json, bestimmt alle 'deployed'-Standards,
klassifiziert sie in Hilfs- und Prüfpakete und kompiliert für jeden
Prüfstandard ein monolithisches JSON-Validierungsprofil.

Aufruf (aus backend/ oder backend/import/):
    python import/parse_xoev_rules.py
    python import/parse_xoev_rules.py --verbose
    python import/parse_xoev_rules.py --registry xrepository/xoev-registry
    python import/parse_xoev_rules.py --output-dir rules/

Ausgabe:
    backend/rules/{standard}_{version}_compiled.json
    z. B. rules/xauslaender_26.11_compiled.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Sicherstellen, dass parser/ importierbar ist, unabhängig vom cwd
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from parser.pipeline import run_pipeline  # noqa: E402

# ── Standardpfade (relativ zu backend/) ───────────────────────────────────────

_BACKEND         = _HERE.parent
_DEFAULT_CONFIG  = _HERE / "config.json"
_DEFAULT_REG     = _BACKEND / "xrepository" / "xoev-registry"
_DEFAULT_OUT     = _BACKEND / "rules"


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "XÖV Profil-Compiler — liest config.json und kompiliert "
            "monolithische JSON-Validierungsprofile fuer alle deployed-Standards."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python import/parse_xoev_rules.py\n"
            "  python import/parse_xoev_rules.py -v\n"
            "  python import/parse_xoev_rules.py --registry xrepository/xoev-registry\n"
            "  python import/parse_xoev_rules.py --output-dir /tmp/profiles\n"
        ),
    )
    ap.add_argument(
        "--config", type=Path, default=_DEFAULT_CONFIG, metavar="PATH",
        help=(
            f"Pfad zur config.json "
            f"(Standard: {_DEFAULT_CONFIG.relative_to(_BACKEND)})"
        ),
    )
    ap.add_argument(
        "--registry", type=Path, default=_DEFAULT_REG, metavar="DIR",
        help=(
            "Registry-Wurzelverzeichnis mit catalog.xml und "
            "Unterordner {domain_path}/{version}/xsd|codelisten/ "
            "(Standard: xrepository/xoev-registry)"
        ),
    )
    ap.add_argument(
        "--output-dir", dest="output_dir", type=Path,
        default=_DEFAULT_OUT, metavar="DIR",
        help="Ausgabeverzeichnis fuer JSON-Profile (Standard: rules/)",
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true",
        help="DEBUG-Logging aktivieren",
    )
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    run_pipeline(
        config_path   = args.config,
        registry_root = args.registry,
        output_dir    = args.output_dir,
        verbose       = args.verbose,
    )


if __name__ == "__main__":
    main()
