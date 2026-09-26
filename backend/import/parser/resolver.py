"""
resolver.py — OASIS XML Catalog 1.1 Resolver für Offline-XÖV-Parsing.

Unterstützte Katalog-Direktiven:
  <system>        — exakte systemId → lokale URI (höchste Priorität)
  <uri>           — exakte URI → lokale URI
  <rewriteSystem> — Präfix-Umschreibung für systemId
  <rewriteURI>    — Präfix-Umschreibung für URI
  <nextCatalog>   — Ketten-Kataloge (mit Zyklus-Schutz)

Wird in zwei Modi genutzt:
  1. Als lxml.etree.Resolver — lxml ruft resolve() bei externen Ressourcen auf.
  2. Direkt via locate(url) — für manuelle xs:import-Verfolgung im XSD-Parser.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from . import _local_name

log = logging.getLogger(__name__)


class OASISCatalogResolver(etree.Resolver):
    """
    Liest catalog.xml und übersetzt externe URIs in lokale Dateipfade.

    Args:
        catalog_path:  Absoluter oder relativer Pfad zu catalog.xml.
        fallback_dirs: Verzeichnisse für den Dateiname-only-Fallback (z. B.
                       XInneres-XSD-Dir), falls keine Katalog-Regel greift.
    """

    def __init__(
        self,
        catalog_path: Path,
        fallback_dirs: list[Path] | None = None,
    ) -> None:
        super().__init__()
        self._base_dir      = catalog_path.parent.resolve()
        self._exact:         dict[str, Path]          = {}
        self._rewrites:      list[tuple[str, Path]]   = []
        self._fallback_dirs: list[Path]               = fallback_dirs or []
        self._loaded:        set[str]                 = set()   # Zyklus-Schutz

        self._load_catalog(catalog_path)
        log.info(
            "Catalog geladen: %d exakte Einträge | %d Rewrite-Regeln | %d Fallback-Dirs",
            len(self._exact), len(self._rewrites), len(self._fallback_dirs),
        )

    # ── Katalog laden ──────────────────────────────────────────────────────────

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

        # Längster Präfix zuerst — spezifischste Regel gewinnt
        self._rewrites.sort(key=lambda t: -len(t[0]))

    # ── Öffentliche API ────────────────────────────────────────────────────────

    def locate(self, url: str) -> Optional[Path]:
        """
        Übersetzt eine URL in einen lokalen Dateipfad. Gibt None zurück, wenn
        keine Katalog-Regel greift.

        Suchreihenfolge:
          0. Bereits lokaler absoluter Pfad (lxml übergibt manchmal aufgelöste Pfade)
          1. Exakte <system>/<uri>-Einträge
          2. Präfix-Regeln (<rewriteSystem>/<rewriteURI>)
          3. Dateiname-only-Fallback in _fallback_dirs
        """
        if not url:
            return None

        # 0. Lokaler absoluter Pfad — direkt prüfen, kein Catalog-Lookup nötig
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
                try:
                    candidate = base_dir / suffix
                    if candidate.exists():
                        return candidate
                except (ValueError, OSError):
                    pass
                # Flat-Fallback: nur Dateiname (häufigste lokale Paketstruktur)
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
        #    Schützt vor Dateinamen mit ':' (URN-Fragmente, Windows-ungültig).
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

    # ── lxml Resolver Interface ────────────────────────────────────────────────

    def resolve(self, url: str, id: str, context):
        """Wird von lxml aufgerufen, wenn eine externe Ressource geladen werden soll."""
        local = self.locate(url)
        if local:
            return self.resolve_filename(str(local), context)
        if url and url.startswith(("http://", "https://")):
            log.warning("Nicht aufgelöste externe URL: %s", url)
        return None
