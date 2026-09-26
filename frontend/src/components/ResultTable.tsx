import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  Download, Info,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Filter,
  ChevronDown, Search, X, Check, SkipForward, RefreshCw, Loader2,
} from "lucide-react";
import { ValidationReport, ValidationError, FieldDef, ColumnMapping } from "../api";

// ─────────────────────────────────────────────────────────────────────────────
// Pure helpers
// ─────────────────────────────────────────────────────────────────────────────

function colIndexToLetter(idx: number): string {
  let result = "";
  let n = idx + 1;
  while (n > 0) {
    result = String.fromCharCode(65 + (n - 1) % 26) + result;
    n = Math.floor((n - 1) / 26);
  }
  return result;
}

const COL_LABELS: Record<string, string> = {
  geschlecht:           "Geschlecht",
  staatsangehoerigkeit: "Staatsangehörigkeit",
  geburtsdatum:         "Geburtsdatum",
  identifikationsnummer:"Identifikationsnummer",
  anschrift_plz:        "Anschrift PLZ",
  gemeindeschluessel:   "Gemeindeschlüssel",
  gewerbe_art:          "Gewerbe Art",
  azr_nummer:           "AZR-Nummer",
  iban:                 "IBAN",
  nachname:             "Nachname",
  vorname:              "Vorname",
  strassenname:         "Straßenname",
  hausnummer:           "Hausnummer",
  wohnort:              "Wohnort",
  postleitzahl:         "Postleitzahl",
};

function colLabel(col: string): string {
  const k = col.toLowerCase();
  return COL_LABELS[k] ?? (k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, " "));
}

const MAX_HDR_LEN = 22;
function truncateLabel(s: string): string {
  return s.length > MAX_HDR_LEN ? s.slice(0, MAX_HDR_LEN) + "…" : s;
}

function errBadgeClass(t: string): string {
  const u = t.toUpperCase();
  if (u.includes("WARNUNG"))
    return "bg-amber-50 text-amber-800 border border-amber-600";
  if (u.includes("LEER") || u.includes("PFLICHT") || u.includes("FEHLT"))
    return "bg-orange-50 text-orange-800 border border-orange-600";
  if (u.includes("STEUER") || u.includes("IBAN"))
    return "bg-purple-50 text-purple-800 border border-purple-600";
  if (u.includes("DATUM") || u.includes("DATE"))
    return "bg-blue-50 text-blue-800 border border-blue-600";
  return "bg-red-50 text-red-800 border border-red-600";
}

function normKey(s: string): string {
  return s.toLowerCase().replace(/[\s._\-]+/g, "");
}

function autoMatchKey(col: string, fields: FieldDef[]): string | null {
  const needle = normKey(col.trim());
  return fields.find(f => normKey(f.key) === needle)?.key ?? null;
}

// ─────────────────────────────────────────────────────────────────────────────
// CSV export (BSI: UTF-8 BOM + formula sanitization)
// ─────────────────────────────────────────────────────────────────────────────

const UNSAFE_RE = /^[=+\-@]/;
function sanitize(v: string) { return UNSAFE_RE.test(v) ? `'${v}` : v; }
function csvEscape(v: string) {
  const s = sanitize(v);
  return s.includes(",") || s.includes('"') || s.includes("\n")
    ? `"${s.replace(/"/g, '""')}"` : s;
}
function exportCsv(report: ValidationReport) {
  const BOM  = "﻿";
  const hdr  = ["Zeilenindex", "Spaltenname", "Ungültiger_Wert", "Fehlertyp", "Korrekturhinweis"];
  const body = report.errors.map(e => [
    String(e.row_index), e.column_name, e.invalid_value, e.error_type, e.fix_suggestion,
  ]);
  const csv = BOM + [hdr, ...body].map(r => r.map(csvEscape).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
  const a   = Object.assign(document.createElement("a"), {
    href: url,
    download: `Korrekturbericht_${report.schema_id}_${new Date().toISOString().slice(0, 10)}.csv`,
  });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tooltip positioning
// ─────────────────────────────────────────────────────────────────────────────

const TIP_W = 288;
const TIP_H = 150;

function calcTipStyle(r: DOMRect): React.CSSProperties {
  const showAbove = r.top > TIP_H + 16;
  const top  = showAbove ? r.top - TIP_H - 6 : r.bottom + 6;
  const left = Math.max(8, Math.min(r.left, window.innerWidth - TIP_W - 8));
  return { position: "fixed", top, left, zIndex: 9999, width: TIP_W };
}

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

const PAGE_SIZES = [20, 50, 100, 200] as const;
type PageSize = typeof PAGE_SIZES[number];

interface TooltipState   { error: ValidationError; cellRect: DOMRect; }
interface HeaderTipState { col: string; rect: DOMRect; }
interface ComboState     { col: string; rect: DOMRect; }

interface Props {
  report:        ValidationReport;
  originalFile:  File | null;
  fields?:       FieldDef[];
  onRevalidate?: (mapping: ColumnMapping) => void;
  revalidating?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Column-header tooltip
// ─────────────────────────────────────────────────────────────────────────────

function HeaderTip({ col, rect, report }: { col: string; rect: DOMRect; report: ValidationReport }) {
  const meta  = report.field_meta?.[col];
  const short = meta?.display_name_short || "";
  const long  = meta?.display_name_long  || "";
  return (
    <div role="tooltip" style={calcTipStyle(rect)}
      className="pointer-events-none border border-[#D1D5DB] bg-white p-3">
      <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-[#555555]">Spaltenname</p>
      <p className="text-xs font-mono text-[#222222] break-all leading-snug">{colLabel(col)}</p>
      {short && <p className="mt-2 text-xs font-medium text-[#555555]">{short}</p>}
      {long  && <p className="mt-0.5 text-xs text-[#555555] leading-snug">{long}</p>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pagination button
// ─────────────────────────────────────────────────────────────────────────────

function PagBtn({ label, icon, disabled, onClick }: {
  label: string; icon: React.ReactNode; disabled: boolean; onClick: () => void;
}) {
  return (
    <button type="button" title={label} aria-label={label} disabled={disabled} onClick={onClick}
      className="flex items-center justify-center border border-[#D1D5DB] bg-white p-1.5
                 text-[#555555] hover:bg-[#F4F6F8] hover:text-[#222222]
                 disabled:opacity-30 disabled:cursor-not-allowed
                 focus:outline-none focus:ring-2 focus:ring-[#FFBF47] focus:ring-offset-2 transition-colors">
      {icon}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Combo dropdown portal
// ─────────────────────────────────────────────────────────────────────────────

const COMBO_DROP_H = 300;

interface ComboDropProps {
  open:        ComboState | null;
  fields:      FieldDef[];
  currentKey:  string | null | undefined;
  highlight:   number;
  dropRef:     React.RefObject<HTMLDivElement | null>;
  inputRef:    React.RefObject<HTMLInputElement | null>;
  onHighlight: (i: number) => void;
  onSelect:    (key: string | null) => void;
  onFiltered:  (list: FieldDef[]) => void;
}

function ComboDropdown({
  open, currentKey, highlight, fields,
  dropRef, inputRef, onHighlight, onSelect, onFiltered,
}: ComboDropProps) {
  const [query, setQuery] = useState("");

  useEffect(() => { setQuery(""); }, [open?.col]);

  const q        = query.toLowerCase().trim();
  const filtered = q ? fields.filter(f => f.key.toLowerCase().startsWith(q)) : fields;
  onFiltered(filtered);

  if (!open) return null;

  const spaceBelow = window.innerHeight - open.rect.bottom;
  const top  = spaceBelow > COMBO_DROP_H
    ? open.rect.bottom + 2
    : open.rect.top - COMBO_DROP_H - 2;
  const left  = Math.min(open.rect.left, window.innerWidth - 300 - 8);
  const width = Math.max(open.rect.width, 300);

  return createPortal(
    <div
      ref={dropRef}
      style={{ position: "fixed", top, left, width, zIndex: 9999 }}
      className="flex flex-col border border-[#D1D5DB] bg-white"
    >
      {/* Suchfeld */}
      <div className="flex items-center gap-2 border-b border-[#D1D5DB] bg-[#F4F6F8] px-2.5 py-1.5">
        <Search className="h-3.5 w-3.5 shrink-0 text-[#555555]" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => { setQuery(e.target.value); onHighlight(0); }}
          placeholder="Feld suchen…"
          className="flex-1 bg-transparent text-xs text-[#222222] placeholder-[#999] outline-none"
          aria-label="Feld suchen"
        />
        {query && (
          <button type="button" onClick={() => { setQuery(""); inputRef.current?.focus(); }}
            className="text-[#555555] hover:text-[#222222]
                       focus:outline-none focus:ring-1 focus:ring-[#FFBF47]"
            aria-label="Suche löschen">
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Optionsliste */}
      <ul key={q} role="listbox"
        style={{ maxHeight: COMBO_DROP_H - 60, overflowY: "auto" }}
        className="py-0.5">

        {/* Spalte überspringen */}
        <li role="option" aria-selected={currentKey == null}
          onClick={() => onSelect(null)}
          className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs transition-colors
            ${highlight === 0
              ? "bg-[#003366] text-white"
              : "text-[#555555] hover:bg-[#F4F6F8]"}`}
        >
          <SkipForward className="h-3 w-3 shrink-0" />
          <span className="italic">— Spalte überspringen —</span>
          {currentKey == null && <Check className="ml-auto h-3 w-3" />}
        </li>

        {filtered.length === 0 && (
          <li className="px-3 py-3 text-center text-xs text-[#555555]">
            Keine Felder gefunden.
          </li>
        )}

        {filtered.map((f, i) => {
          const isActive = f.key === currentKey;
          const isHi     = i + 1 === highlight;
          return (
            <li key={f.key} role="option" aria-selected={isActive}
              onClick={() => onSelect(f.key)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs transition-colors
                ${isHi
                  ? "bg-[#003366] text-white"
                  : isActive
                    ? "bg-[#EEF4FA] text-[#003366]"
                    : "text-[#222222] hover:bg-[#F4F6F8]"}`}
            >
              <span className="min-w-0 flex-1 truncate">{f.label}</span>
              {f.has_codelist === false && (
                <span
                  title="Bekanntes XÖV-Feld ohne Codelisten-Prüfung"
                  className={`shrink-0 border px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide
                    ${isHi
                      ? "border-white/40 text-white/80"
                      : "border-[#D1D5DB] text-[#555555]"}`}
                >
                  XÖV
                </span>
              )}
              {isActive && <Check className="h-3 w-3 shrink-0" />}
            </li>
          );
        })}
      </ul>

      {/* Fußzeile */}
      <div className="border-t border-[#D1D5DB] px-3 py-1 text-right text-[10px] text-[#555555]">
        {query ? `${filtered.length} Treffer` : `${fields.length} Felder`}
      </div>
    </div>,
    document.body,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function ResultTable({ report, fields, onRevalidate, revalidating }: Props) {
  const [tip,          setTip]          = useState<TooltipState | null>(null);
  const [filterErrors, setFilterErrors] = useState(false);
  const [pageSize,     setPageSize]     = useState<PageSize>(50);
  const [currentPage,  setCurrentPage]  = useState(0);
  const [headerTip,    setHeaderTip]    = useState<HeaderTipState | null>(null);

  const [colMapping,  setColMapping]  = useState<Record<string, string | null>>({});
  const [touchedCols, setTouchedCols] = useState<Set<string>>(new Set());
  const [openCombo,   setOpenCombo]   = useState<ComboState | null>(null);
  const [comboHi,     setComboHi]     = useState(0);

  const comboInputRef    = useRef<HTMLInputElement>(null);
  const comboDropRef     = useRef<HTMLDivElement>(null);
  const triggerRefs      = useRef<Record<string, HTMLButtonElement | null>>({});
  const filteredComboRef = useRef<FieldDef[]>([]);

  const headers     = report.headers ?? [];
  const rows        = report.rows    ?? [];
  const hasZeile    = headers.includes("zeile");
  const dataHeaders = useMemo(() => headers.filter(h => h !== "zeile"), [headers]);

  const headersKey = dataHeaders.join("|");
  useEffect(() => {
    if (!fields?.length || !dataHeaders.length) return;
    setColMapping(prev => {
      const next: Record<string, string | null> = {};
      for (const h of dataHeaders) {
        next[h] = h in prev ? prev[h] : autoMatchKey(h, fields);
      }
      return next;
    });
    setTouchedCols(prev => {
      const next = new Set<string>();
      for (const t of prev) if (dataHeaders.includes(t)) next.add(t);
      return next;
    });
    setOpenCombo(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headersKey, fields]);

  useEffect(() => {
    if (openCombo) setTimeout(() => comboInputRef.current?.focus(), 20);
  }, [openCombo?.col]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!openCombo) return;
    const handler = (e: MouseEvent) => {
      const t = e.target as Node;
      if (comboDropRef.current?.contains(t)) return;
      for (const btn of Object.values(triggerRefs.current)) {
        if (btn?.contains(t)) return;
      }
      setOpenCombo(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [openCombo]);

  useEffect(() => {
    if (!openCombo) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenCombo(null);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setComboHi(i => Math.min(i + 1, filteredComboRef.current.length));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setComboHi(i => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const key = comboHi === 0 ? null : filteredComboRef.current[comboHi - 1]?.key ?? null;
        selectMapping(openCombo.col, key);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [openCombo, comboHi]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!openCombo) return;
    const update = () => {
      const btn = triggerRefs.current[openCombo.col];
      if (btn) setOpenCombo(prev => prev ? { col: prev.col, rect: btn.getBoundingClientRect() } : prev);
    };
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [openCombo?.col]); // eslint-disable-line react-hooks/exhaustive-deps

  function openDropdown(col: string, e: React.MouseEvent<HTMLButtonElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    setOpenCombo(prev => prev?.col === col ? null : { col, rect });
    setComboHi(0);
  }

  function selectMapping(col: string, key: string | null) {
    setColMapping(prev => ({ ...prev, [col]: key }));
    setTouchedCols(prev => new Set([...prev, col]));
    setOpenCombo(null);
    setComboHi(0);
  }

  function buildMapping(): ColumnMapping {
    const out: ColumnMapping = {};
    for (const h of dataHeaders) {
      const val = colMapping[h];
      if (touchedCols.has(h)) {
        out[h] = val;
      } else if (val !== null && val !== h) {
        out[h] = val;
      }
    }
    return out;
  }

  const errMap = useMemo(() => {
    const m: Record<string, ValidationError> = {};
    for (const e of report.errors) {
      if (e.row_index > 0) m[`${e.row_index}_${e.column_name.toLowerCase()}`] = e;
    }
    return m;
  }, [report.errors]);

  const warnMap = useMemo(() => {
    const m: Record<string, ValidationError> = {};
    for (const w of (report.warnings ?? [])) {
      if (w.row_index > 0) m[`${w.row_index}_${w.column_name.toLowerCase()}`] = w;
    }
    return m;
  }, [report.warnings]);

  const structErrors = useMemo(
    () => report.errors.filter(e => e.row_index === 0),
    [report.errors],
  );

  const headerErrMap = useMemo(() => {
    const m: Record<string, ValidationError> = {};
    for (const e of structErrors) m[e.column_name] = e;
    return m;
  }, [structErrors]);

  const rowsWithIdx = useMemo(
    () => rows.map((row, arrayIdx) => ({ row, arrayIdx })),
    [rows],
  );

  const rowHasError = useCallback(
    (arrayIdx: number) => dataHeaders.some(h => `${arrayIdx + 1}_${h}` in errMap),
    [dataHeaders, errMap],
  );

  const filteredRows = useMemo(
    () => filterErrors ? rowsWithIdx.filter(({ arrayIdx }) => rowHasError(arrayIdx)) : rowsWithIdx,
    [rowsWithIdx, filterErrors, rowHasError],
  );

  const errorRowCount = useMemo(
    () => rowsWithIdx.filter(({ arrayIdx }) => rowHasError(arrayIdx)).length,
    [rowsWithIdx, rowHasError],
  );

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const safePage   = Math.min(currentPage, totalPages - 1);
  const pagedRows  = filteredRows.slice(safePage * pageSize, (safePage + 1) * pageSize);

  const onEnter = useCallback(
    (e: React.MouseEvent<HTMLTableCellElement>, err: ValidationError) =>
      setTip({ error: err, cellRect: e.currentTarget.getBoundingClientRect() }),
    [],
  );
  const onLeave       = useCallback(() => setTip(null), []);
  const onHeaderEnter = useCallback(
    (e: React.MouseEvent<HTMLTableCellElement>, col: string) =>
      setHeaderTip({ col, rect: e.currentTarget.getBoundingClientRect() }),
    [],
  );
  const onHeaderLeave = useCallback(() => setHeaderTip(null), []);

  // Doppelter horizontaler Scrollbalken
  const tableWrapperRef = useRef<HTMLDivElement>(null);
  const fakeScrollRef   = useRef<HTMLDivElement>(null);
  const innerFakeRef    = useRef<HTMLDivElement>(null);
  const isSyncing       = useRef(false);

  useEffect(() => {
    const wrapper = tableWrapperRef.current;
    const inner   = innerFakeRef.current;
    if (!wrapper || !inner) return;
    const sync = () => {
      if (tableWrapperRef.current && innerFakeRef.current)
        innerFakeRef.current.style.width = `${tableWrapperRef.current.scrollWidth}px`;
    };
    const rafId = requestAnimationFrame(sync);
    const ro = new ResizeObserver(sync);
    ro.observe(wrapper);
    return () => { cancelAnimationFrame(rafId); ro.disconnect(); };
  }, [dataHeaders, pagedRows]);

  const handleFakeScroll = useCallback(() => {
    if (isSyncing.current) return;
    const fake = fakeScrollRef.current; const wrapper = tableWrapperRef.current;
    if (!fake || !wrapper) return;
    isSyncing.current = true;
    wrapper.scrollLeft = fake.scrollLeft;
    requestAnimationFrame(() => { isSyncing.current = false; });
  }, []);

  const handleTableScroll = useCallback(() => {
    if (isSyncing.current) return;
    const fake = fakeScrollRef.current; const wrapper = tableWrapperRef.current;
    if (!fake || !wrapper) return;
    isSyncing.current = true;
    fake.scrollLeft = wrapper.scrollLeft;
    requestAnimationFrame(() => { isSyncing.current = false; });
  }, []);

  // ── Fehlerfrei ────────────────────────────────────────────────────────────
  if (report.error_count === 0 && (report.warning_count ?? 0) === 0) {
    return (
      <div className="mt-6 flex items-center gap-3 border-l-4 border-green-600 bg-green-50 px-5 py-4 text-green-800">
        <Info className="h-5 w-5 shrink-0" aria-hidden="true" />
        <p className="text-sm font-medium">
          Alle {report.total_rows.toLocaleString("de-DE")} Datensätze sind fehlerfrei. Keine Korrekturen erforderlich.
        </p>
      </div>
    );
  }

  if (headers.length === 0) {
    return (
      <div className="mt-6 flex items-center justify-between border border-[#D1D5DB] bg-white px-5 py-4 text-sm text-[#555555]">
        <span>Keine Vorschaudaten verfügbar (veraltete Backend-Version).</span>
        <button onClick={() => exportCsv(report)}
          className="ml-4 text-[#003366] hover:text-[#005B9A] underline
                     focus:outline-none focus:ring-2 focus:ring-[#FFBF47]">
          Korrekturbericht exportieren (.csv)
        </button>
      </div>
    );
  }

  const showMappingRow = !!(fields?.length);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <section aria-labelledby="grid-title" className="mt-6">

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
        <h2 id="grid-title" className="text-sm font-semibold text-[#222222]">
          Dateivorschau — {report.schema_name}
        </h2>
        <div className="flex items-center gap-2">
          {onRevalidate && showMappingRow && (
            <button type="button"
              onClick={() => onRevalidate(buildMapping())}
              disabled={revalidating}
              className="inline-flex items-center gap-2 border border-[#003366] bg-white
                         px-4 py-2 text-sm font-medium text-[#003366] hover:bg-[#EEF4FA] transition-colors
                         focus:outline-none focus:ring-2 focus:ring-[#FFBF47] focus:ring-offset-2
                         disabled:opacity-40 disabled:cursor-not-allowed"
              title="Datei mit aktueller Spalten-Zuordnung neu validieren"
            >
              {revalidating
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <RefreshCw className="h-4 w-4" />}
              Neu validieren
            </button>
          )}
          <button type="button" onClick={() => exportCsv(report)}
            className="inline-flex items-center gap-2 bg-[#003366] px-4 py-2 text-sm font-medium
                       text-white hover:bg-[#005B9A] transition-colors
                       focus:outline-none focus:ring-2 focus:ring-[#FFBF47] focus:ring-offset-2"
            aria-label="Korrekturbericht als CSV herunterladen">
            <Download className="h-4 w-4" aria-hidden="true" />
            Korrekturbericht (.csv)
          </button>
        </div>
      </div>

      {/* Steuerleiste */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mb-3 px-1">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <button type="button" role="switch" aria-checked={filterErrors}
            onClick={() => { setFilterErrors(v => !v); setCurrentPage(0); }}
            className={`relative inline-flex h-5 w-9 items-center transition-colors
                        focus:outline-none focus:ring-2 focus:ring-[#FFBF47] focus:ring-offset-2
                        ${filterErrors ? "bg-red-600" : "bg-[#D1D5DB]"}`}>
            <span className={`inline-block h-3.5 w-3.5 bg-white transition-transform
                              ${filterErrors ? "translate-x-[18px]" : "translate-x-[3px]"}`} />
          </button>
          <span className="flex items-center gap-1.5 text-sm text-[#222222]">
            <Filter className="h-3.5 w-3.5 text-[#555555]" aria-hidden="true" />
            Nur Fehlerzeilen
            {filterErrors && (
              <span className="ml-1 border border-red-600 bg-red-50 px-1.5 py-0.5 text-xs text-red-800">
                {errorRowCount.toLocaleString("de-DE")} Zeilen
              </span>
            )}
          </span>
        </label>

        <div className="ml-auto flex items-center gap-2">
          <label htmlFor="page-size-select" className="text-xs text-[#555555] whitespace-nowrap">
            Zeilen / Seite:
          </label>
          <select id="page-size-select" value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value) as PageSize); setCurrentPage(0); }}
            className="border border-[#D1D5DB] bg-white px-2 py-1 text-xs text-[#222222]
                       focus:outline-none focus:ring-2 focus:ring-[#FFBF47]">
            {PAGE_SIZES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {/* Tabelle mit doppeltem Scrollbalken */}
      <div className="border border-[#D1D5DB] overflow-hidden">

        <div ref={fakeScrollRef} onScroll={handleFakeScroll}
          className="overflow-x-auto overflow-y-hidden border-b border-[#D1D5DB] bg-[#F4F6F8]"
          style={{ height: 14 }} aria-hidden="true">
          <div ref={innerFakeRef} style={{ height: 1 }} />
        </div>

        <div ref={tableWrapperRef} onScroll={handleTableScroll} className="overflow-x-auto">
          <table className="border-collapse text-xs"
            style={{ minWidth: `${dataHeaders.length * 130 + 52}px` }}
            role="grid" aria-label={`Dateivorschau: ${report.schema_name}`}>
            <thead>

              {/* Reihe 1: Spaltenbuchstaben */}
              <tr className="border-b border-[#002244] bg-[#003366]">
                <th scope="col" aria-hidden="true"
                  className="sticky left-0 z-20 w-12 min-w-[3rem] border-r border-[#002244]
                             bg-[#003366] px-2 py-1.5" />
                {dataHeaders.map((_, i) => (
                  <th key={i} scope="col"
                    className="min-w-[130px] whitespace-nowrap border-r border-[#002244]
                               px-2 py-1.5 text-center font-mono text-[11px] font-medium text-white/60">
                    {colIndexToLetter(i)}
                  </th>
                ))}
              </tr>

              {/* Reihe 2: Spaltennamen */}
              <tr className="border-b border-[#D1D5DB] bg-[#F4F6F8]">
                <th scope="col" aria-label="Zeilennummer"
                  className="sticky left-0 z-20 w-12 min-w-[3rem] border-r border-[#D1D5DB]
                             bg-[#F4F6F8] px-2 py-2 text-center text-[11px] font-normal text-[#555555]">
                  #
                </th>
                {dataHeaders.map(h => {
                  const hErr = headerErrMap[h];
                  return (
                    <th key={h} scope="col"
                      className={`min-w-[130px] cursor-help whitespace-nowrap border-r px-3 py-2
                                  text-left font-semibold transition-colors
                                  ${hErr
                                    ? "border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100"
                                    : "border-[#D1D5DB] text-[#222222] hover:bg-white"
                                  }`}
                      onMouseEnter={e => {
                        if (hErr) { onHeaderLeave(); onEnter(e as React.MouseEvent<HTMLTableCellElement>, hErr); }
                        else      { onLeave(); onHeaderEnter(e, h); }
                      }}
                      onMouseLeave={() => { onLeave(); onHeaderLeave(); }}
                      aria-label={hErr
                        ? `${colLabel(h)}: Hinweis — Spalte nicht im Validierungsprofil`
                        : undefined}
                    >
                      {hErr && (
                        <span className="mr-1.5 inline-block h-1.5 w-1.5 bg-amber-500" aria-hidden="true" />
                      )}
                      {truncateLabel(colLabel(h))}
                    </th>
                  );
                })}
              </tr>

              {/* Reihe 3: Mapping-Comboboxen */}
              {showMappingRow && (
                <tr className="border-b border-[#D1D5DB] bg-white">
                  <th scope="col"
                    className="sticky left-0 z-20 w-12 min-w-[3rem] border-r border-[#D1D5DB]
                               bg-white px-2 py-1.5 text-center text-[10px] text-[#555555]"
                    aria-label="Spalten-Zuordnung">
                    ↔
                  </th>
                  {dataHeaders.map(h => {
                    const mappedKey   = colMapping[h];
                    const isMatched   = mappedKey != null;
                    const isSkipped   = mappedKey === null && touchedCols.has(h);
                    const isOpen      = openCombo?.col === h;
                    const mappedField = (mappedKey && fields) ? fields.find(f => f.key === mappedKey) : null;

                    return (
                      <th key={h} scope="col"
                        className="min-w-[130px] border-r border-[#D1D5DB]/60 px-1.5 py-1 font-normal">
                        <button
                          ref={el => { triggerRefs.current[h] = el; }}
                          type="button"
                          onClick={e => openDropdown(h, e)}
                          aria-haspopup="listbox"
                          aria-expanded={isOpen}
                          aria-label={`Spalte ${h} zuordnen`}
                          className={`flex w-full items-center justify-between gap-1 border
                                      px-2 py-1 text-[11px] transition-colors
                                      focus:outline-none focus:ring-2 focus:ring-[#FFBF47]
                                      ${isMatched
                                        ? "border-green-600 bg-green-50 text-green-800 hover:bg-green-100"
                                        : isSkipped
                                          ? "border-[#D1D5DB] bg-white text-[#555555] hover:bg-[#F4F6F8]"
                                          : "border-red-600 bg-red-50 text-red-800 hover:bg-red-100"
                                      }
                                      ${isOpen ? "ring-2 ring-[#FFBF47]" : ""}`}
                        >
                          <span className="min-w-0 flex-1 truncate font-normal">
                            {mappedField
                              ? mappedField.label
                              : isSkipped
                                ? "— überspringen —"
                                : "Nicht zugeordnet"}
                          </span>
                          <ChevronDown
                            className={`h-3 w-3 shrink-0 opacity-60 transition-transform ${isOpen ? "rotate-180" : ""}`}
                            aria-hidden="true"
                          />
                        </button>
                      </th>
                    );
                  })}
                </tr>
              )}

            </thead>
            <tbody>
              {pagedRows.length === 0 && (
                <tr>
                  <td colSpan={dataHeaders.length + 1}
                    className="px-6 py-8 text-center text-sm text-[#555555]">
                    Keine Datenzeilen vorhanden.
                  </td>
                </tr>
              )}
              {pagedRows.map(({ row, arrayIdx }) => {
                const rowIdx   = arrayIdx + 1;
                const zeileVal = hasZeile ? (row["zeile"] || String(rowIdx)) : String(rowIdx);
                const rowHasErr = dataHeaders.some(h => `${rowIdx}_${h}` in errMap);

                return (
                  <tr key={arrayIdx}
                    className={`border-b border-[#D1D5DB]/40 transition-colors
                                ${rowHasErr
                                  ? "bg-red-50/40"
                                  : "even:bg-[#F8F9FA] hover:bg-[#EEF4FA]/60"}`}>
                    <td className="sticky left-0 z-10 w-12 min-w-[3rem] select-none whitespace-nowrap
                                   border-r border-[#D1D5DB] bg-[#F4F6F8]
                                   px-2 py-1.5 text-center font-mono text-[#555555]">
                      {zeileVal}
                    </td>
                    {dataHeaders.map(h => {
                      const key  = `${rowIdx}_${h}`;
                      const err  = errMap[key];
                      const warn = warnMap[key];
                      const val  = String(row[h] ?? "");

                      if (err) return (
                        <td key={h}
                          className="min-w-[130px] cursor-help border border-red-400
                                     bg-red-50 px-3 py-1.5 transition-colors hover:bg-red-100"
                          onMouseEnter={e => onEnter(e, err)} onMouseLeave={onLeave}
                          aria-label={`${colLabel(h)}: Fehler — ${err.error_type}`}>
                          {val
                            ? <span className="font-mono text-red-800">{val}</span>
                            : <em className="not-italic text-red-400">∅ leer</em>}
                        </td>
                      );

                      if (warn) return (
                        <td key={h}
                          className="min-w-[130px] cursor-help border border-amber-400
                                     bg-amber-50 px-3 py-1.5 transition-colors hover:bg-amber-100"
                          onMouseEnter={e => onEnter(e, warn)} onMouseLeave={onLeave}
                          aria-label={`${colLabel(h)}: Hinweis — ${warn.error_type}`}>
                          <em className="not-italic text-amber-700">∅ leer</em>
                        </td>
                      );

                      return (
                        <td key={h}
                          className="min-w-[130px] whitespace-nowrap border-r border-[#D1D5DB]/40
                                     px-3 py-1.5 text-[#222222]">
                          {val || <span className="text-[#D1D5DB]">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Paginierung */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1">
        <span className="text-xs text-[#555555]">
          {filteredRows.length.toLocaleString("de-DE")} Zeilen
          {filterErrors ? " (nur Fehler)" : ""}
          {" · Seite "}
          <strong className="text-[#222222]">{safePage + 1}</strong>
          {" von "}
          <strong className="text-[#222222]">{totalPages}</strong>
        </span>
        <div className="flex items-center gap-1">
          <PagBtn label="Erste Seite"     icon={<ChevronsLeft  className="h-4 w-4" />} disabled={safePage === 0}              onClick={() => setCurrentPage(0)} />
          <PagBtn label="Vorherige Seite" icon={<ChevronLeft   className="h-4 w-4" />} disabled={safePage === 0}              onClick={() => setCurrentPage(p => Math.max(0, p - 1))} />
          <span className="min-w-[5rem] border border-[#D1D5DB] bg-white px-3 py-1.5 text-center text-xs text-[#222222]">
            {safePage + 1} / {totalPages}
          </span>
          <PagBtn label="Nächste Seite"   icon={<ChevronRight  className="h-4 w-4" />} disabled={safePage >= totalPages - 1} onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))} />
          <PagBtn label="Letzte Seite"    icon={<ChevronsRight className="h-4 w-4" />} disabled={safePage >= totalPages - 1} onClick={() => setCurrentPage(totalPages - 1)} />
        </div>
      </div>

      {/* Portale */}

      <ComboDropdown
        open={openCombo}
        fields={fields ?? []}
        currentKey={openCombo ? colMapping[openCombo.col] : undefined}
        highlight={comboHi}
        dropRef={comboDropRef}
        inputRef={comboInputRef}
        onHighlight={setComboHi}
        onSelect={key => openCombo && selectMapping(openCombo.col, key)}
        onFiltered={list => { filteredComboRef.current = list; }}
      />

      {headerTip && createPortal(
        <HeaderTip col={headerTip.col} rect={headerTip.rect} report={report} />,
        document.body,
      )}

      {tip && createPortal(
        <div role="tooltip" style={calcTipStyle(tip.cellRect)}
          className="pointer-events-none border border-[#D1D5DB] bg-white p-3">
          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-[#555555]">Fehlertyp</p>
          <span className={`mb-3 inline-block px-2 py-0.5 text-xs font-medium ${errBadgeClass(tip.error.error_type)}`}>
            {tip.error.error_type}
          </span>
          <p className="mb-1 text-xs font-semibold text-[#222222]">Korrekturhinweis</p>
          <p className="text-xs leading-relaxed text-[#555555]">{tip.error.fix_suggestion}</p>
        </div>,
        document.body,
      )}

    </section>
  );
}
