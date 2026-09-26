"""
pipeline.py — Dynamischer Konveyeur zur Kompilierung von XÖV-Validierungsprofilen.

Liest config.json, trennt Pakete in Auxiliary (Hilfspakete wie XInneres-Basismodul)
und Primary (prüfbare Standards wie XAusländer, XMeld), und erzeugt für jeden
Primary-Standard ein monolithisches JSON-Profil unter output_dir/.

Paket-Klassifizierung (XÖV-Konvention):
  Auxiliary  — standard-Name oder domain_path enthält: basismodul, baukasten, xinneres
  Primary    — alle anderen deployed-Pakete

Ausgabe-Namensschema:
  {schema_id}_{version}_compiled.json
  z. B.  xauslaender_26.11_compiled.json
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from .genericode import GenericodeIndex, enrich_rules_with_codes
from .resolver import OASISCatalogResolver
from .xsd_parser import XOVSchemaParser

log = logging.getLogger(__name__)

# Marker, die ein Paket als Hilfsbaustein kennzeichnen (XÖV-Konvention)
_AUX_MARKERS = frozenset({"basismodul", "baukasten", "xinneres"})


# ── Logging-Setup ─────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt   = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
    logging.basicConfig(stream=sys.stderr, level=level, format=fmt, datefmt="%H:%M:%S")


# ── Paket-Klassifizierung ─────────────────────────────────────────────────────

def _is_auxiliary(pkg: dict) -> bool:
    """
    True wenn das Paket ein Querschnittsbaustein ist (kein eigenes Prüfprofil).
    Entscheidung basiert auf standard-Name und domain_path (case-insensitive).
    """
    needle = (
        pkg.get("standard", "").lower()
        + " "
        + pkg.get("domain_path", "").lower()
    )
    return any(marker in needle for marker in _AUX_MARKERS)


# ── Pfad-Hilfsfunktionen ──────────────────────────────────────────────────────

def _xsd_dir(registry_root: Path, pkg: dict) -> Path:
    return registry_root / pkg["domain_path"] / pkg["version"] / "xsd"


def _codelisten_dir(registry_root: Path, pkg: dict) -> Path:
    return registry_root / pkg["domain_path"] / pkg["version"] / "codelisten"


def _schema_id(pkg: dict) -> str:
    """Normalisierter Bezeichner: 'XInneres-Basismodul' → 'xinneres_basismodul'."""
    return re.sub(r"[^a-z0-9]+", "_", pkg["standard"].lower()).strip("_")


# ── Profil-Builder ────────────────────────────────────────────────────────────

def build_profile(
    catalog:            OASISCatalogResolver,
    standard_label:     str,
    primary_xsd_dirs:   list[Path],
    auxiliary_xsd_dirs: list[Path],
    codelisten_dirs:    list[Path],
    output_path:        Path,
    schema_id:          str,
    schema_name:        str,
    version:            str,
    xoev_standard:      str,
) -> bool:
    """
    Kompiliert ein monolithisches JSON-Validierungsprofil für einen XÖV-Standard.

    Jeder Aufruf erhält eine frische XOVSchemaParser-Instanz (isolierter Typ-Index),
    sodass first-wins-Konflikte zwischen Standards ausgeschlossen sind.
    Der OASISCatalogResolver wird read-only geteilt.

    Gibt True bei Erfolg zurück.
    """
    parser = XOVSchemaParser(catalog)

    # -- Phase 1: Standard-eigene XSDs ----------------------------------------
    log.info("=== [%s] Phase 1: Primaere Schemata parsen ===", standard_label)
    for xsd_dir in primary_xsd_dirs:
        if xsd_dir.is_dir():
            parser.parse_directory(xsd_dir)
        else:
            log.warning("[%s] XSD-Verzeichnis nicht gefunden: %s", standard_label, xsd_dir)

    # -- Phase 2: Querschnitts-XSDs nachindizieren (Typ-Index vervollständigen) -
    for xsd_dir in auxiliary_xsd_dirs:
        if xsd_dir.is_dir():
            log.info(
                "=== [%s] Phase 2: Hilfs-Schemata nachindizieren (%s) ===",
                standard_label, xsd_dir.name,
            )
            parser.parse_directory(xsd_dir)

    # -- Phase 3: Codelisten-Regeln aus XSD-Annotationen extrahieren ----------
    log.info("=== [%s] Phase 3: Codelisten-Regeln extrahieren ===", standard_label)
    rules = parser.extract_rules()

    # -- Phase 4: Genericode-Index aufbauen (URN → Dateipfad) -----------------
    log.info("=== [%s] Phase 4: Genericode-Codelisten indizieren ===", standard_label)
    gc_index = GenericodeIndex(*codelisten_dirs)

    # -- Phase 5: Codes aus XML-Codelisten einbetten ---------------------------
    log.info("=== [%s] Phase 5: Codes aus XML-Codelisten einbetten ===", standard_label)
    enriched_rules, found_count, not_found_count = enrich_rules_with_codes(rules, gc_index)

    # -- Phase 6: JSON-Monolith schreiben --------------------------------------
    monolith = {
        "schema_id":     schema_id,
        "schema_name":   schema_name,
        "version":       version,
        "xoev_standard": xoev_standard,
        "description": (
            f"Monolithisches Validierungsprofil, automatisch kompiliert aus "
            f"XSD-Annotationen und Genericode-Codelisten des {xoev_standard}-Standards v{version}. "
            f"Enthaelt {len(enriched_rules)} Felder, davon {found_count} mit eingebetteten Codes."
        ),
        "fields": enriched_rules,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(monolith, f, ensure_ascii=False, indent=2)

    # -- Zusammenfassung -------------------------------------------------------
    ok_files   = sum(1 for v in parser._parsed.values() if v is not None)
    total_files = len(parser._parsed)
    total_types = len(parser._type_idx)
    with_codes  = sum(1 for r in enriched_rules.values() if r.get("allowed_codes"))

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  [{standard_label}] Monolithisches Profil kompiliert")
    print(sep)
    print(f"  XSD-Dateien verarbeitet      : {ok_files} / {total_files}")
    print(f"  Typen im Index               : {total_types}")
    print(f"  Codelisten-Felder gefunden   : {len(rules)}")
    print(f"  Genericode-Dateien gescannt  : {gc_index.total_scanned}")
    print(f"  Genericode-URNs indiziert    : {gc_index.total_indexed}")
    print(f"  Codes erfolgreich eingebettet: {found_count}  ({with_codes} Felder mit Codes)")
    print(f"  Codelisten nicht gefunden    : {not_found_count}")
    try:
        print(f"  Ausgabedatei                 : {output_path.relative_to(Path.cwd())}")
    except ValueError:
        print(f"  Ausgabedatei                 : {output_path}")
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
    return True


# ── Pipeline-Orchestrierung ───────────────────────────────────────────────────

def run_pipeline(
    config_path:   Path,
    registry_root: Path,
    output_dir:    Path,
    verbose:       bool = False,
) -> None:
    """
    Liest config.json, klassifiziert Pakete, und kompiliert für jeden
    Primary-Standard ein JSON-Profil.

    Args:
        config_path:   Pfad zur config.json.
        registry_root: Wurzelverzeichnis des XÖV-Registry mit catalog.xml und
                       Unterordner-Struktur {domain_path}/{version}/xsd|codelisten/.
        output_dir:    Zielverzeichnis für die kompilierten JSON-Profile.
        verbose:       DEBUG-Logging aktivieren.
    """
    _setup_logging(verbose)

    # -- Config laden ----------------------------------------------------------
    if not config_path.exists():
        log.error("config.json nicht gefunden: %s", config_path)
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    all_packages = [
        p for p in config.get("packages", [])
        if p.get("status") == "deployed"
    ]
    if not all_packages:
        log.warning("Keine 'deployed'-Pakete in config.json gefunden.")
        return

    # -- Pakete klassifizieren -------------------------------------------------
    aux_packages     = [p for p in all_packages if     _is_auxiliary(p)]
    primary_packages = [p for p in all_packages if not _is_auxiliary(p)]

    log.info(
        "Pakete (deployed): %d gesamt — %d Hilfspakete, %d Pruefpakete",
        len(all_packages), len(aux_packages), len(primary_packages),
    )
    for pkg in aux_packages:
        log.info("  [AUX]  %s v%s", pkg["standard"], pkg["version"])
    for pkg in primary_packages:
        log.info("  [MAIN] %s v%s", pkg["standard"], pkg["version"])

    # -- Auxiliary-Pfade sammeln -----------------------------------------------
    aux_xsd_dirs:        list[Path] = []
    aux_codelisten_dirs: list[Path] = []

    for pkg in aux_packages:
        xsd_dir = _xsd_dir(registry_root, pkg)
        cl_dir  = _codelisten_dir(registry_root, pkg)
        if xsd_dir.is_dir():
            aux_xsd_dirs.append(xsd_dir)
            log.info("Hilfs-XSD-Dir registriert        : %s", xsd_dir)
        else:
            log.warning(
                "Hilfspaket '%s': XSD-Verzeichnis nicht gefunden, uebersprungen: %s",
                pkg["standard"], xsd_dir,
            )
        if cl_dir.is_dir():
            aux_codelisten_dirs.append(cl_dir)
            log.info("Hilfs-Codelisten-Dir registriert : %s", cl_dir)
        else:
            log.warning(
                "Hilfspaket '%s': Codelisten-Verzeichnis nicht gefunden: %s",
                pkg["standard"], cl_dir,
            )

    # -- Katalog laden (gemeinsam, read-only für alle Standards) --------------
    catalog_path = registry_root / "catalog.xml"
    if not catalog_path.exists():
        log.error("Katalog nicht gefunden: %s", catalog_path)
        sys.exit(1)

    catalog = OASISCatalogResolver(catalog_path, aux_xsd_dirs)

    # -- Primary-Standards kompilieren ----------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    success = 0

    for pkg in primary_packages:
        std = pkg["standard"]
        ver = pkg["version"]

        xsd_dir = _xsd_dir(registry_root, pkg)
        cl_dir  = _codelisten_dir(registry_root, pkg)

        if not xsd_dir.is_dir():
            log.warning(
                "Pruefpaket '%s': XSD-Verzeichnis nicht gefunden, uebersprungen: %s",
                std, xsd_dir,
            )
            continue

        sid         = _schema_id(pkg)
        schema_id   = f"{sid}_{ver}_compiled"
        output_path = output_dir / f"{schema_id}.json"

        codelisten_dirs = (
            ([cl_dir] if cl_dir.is_dir() else []) + aux_codelisten_dirs
        )

        ok = build_profile(
            catalog            = catalog,
            standard_label     = std,
            primary_xsd_dirs   = [xsd_dir],
            auxiliary_xsd_dirs = aux_xsd_dirs,
            codelisten_dirs    = codelisten_dirs,
            output_path        = output_path,
            schema_id          = schema_id,
            schema_name        = f"{std} Vollpruefung Profile",
            version            = ver,
            xoev_standard      = std,
        )
        if ok:
            success += 1

    log.info(
        "Pipeline abgeschlossen: %d / %d Standards erfolgreich kompiliert.",
        success, len(primary_packages),
    )
