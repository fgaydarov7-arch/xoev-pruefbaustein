"""
XÖV Parser Package — gemeinsame Konstanten und Micro-Helfer.

Alle Untermodule importieren aus diesem __init__, um Duplizierung zu vermeiden.
Außerhalb des Pakets ist dieser Import nicht nötig — Nutzer importieren direkt
aus den spezifischen Untermodulen (resolver, genericode, xsd_parser, pipeline).
"""
from __future__ import annotations

from typing import Optional

from lxml import etree

# ── XML-Namespaces ─────────────────────────────────────────────────────────────

NS_XS      = "http://www.w3.org/2001/XMLSchema"
NS_CATALOG = "urn:oasis:names:tc:entity:xmlns:xml:catalog"
NS_GC      = "http://docs.oasis-open.org/codelist/ns/genericode/1.0/"
NS_CL3     = "http://xoev.de/schemata/genericode/3"   # empfohleneCodeSpalte (XInneres)
NS_CL4     = "http://xoev.de/schemata/genericode/4"   # recommendedKeyColumn (XAusländer)

# ── Bekannte XÖV-URN-Präfixe ──────────────────────────────────────────────────

_XOEV_URN_PREFIXES: tuple[str, ...] = (
    "urn:xoev-de:",        # Dachverband-Präfix (XMeld, XInneres, XBau …)
    "urn:de:xauslaender:", # XAusländer-spezifisch
    "urn:de:bund:",        # Bundesbehörden-Codelisten
)


# ── Micro-Helfer (namespace-agnostisch) ───────────────────────────────────────

def _local_name(el: etree._Element) -> str:
    """{http://...}localname  →  localname."""
    tag = el.tag
    return tag.split("}")[-1] if isinstance(tag, str) and "}" in tag else tag


def _find_child_by_local(
    parent: etree._Element, local: str
) -> Optional[etree._Element]:
    """Erstes direktes Kind-Element mit passendem Local-Name (jeder Namespace)."""
    for child in parent:
        if _local_name(child) == local:
            return child
    return None


def _is_xoev_urn(value: str) -> bool:
    """True wenn value ein bekanntes XÖV-URN-Präfix trägt."""
    return any(value.startswith(p) for p in _XOEV_URN_PREFIXES)
