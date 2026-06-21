import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  Download, Info, AlertTriangle,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Filter,
} from "lucide-react";
import { ValidationReport, ValidationError } from "../api";

// ─────────────────────────────────────────────────────────────────────────────
// Pure helpers
// ─────────────────────────────────────────────────────────────────────────────

/** 0→"A", 25→"Z", 26→"AA", 27→"AB" … works for any number of columns. */
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
  geschlecht: "Geschlecht",
  staatsangehoerigkeit: "Staatsangehörigkeit",
  geburtsdatum: "Geburtsdatum",
  identifikationsnummer: "Identifikationsnummer",
  anschrift_plz: "Anschrift PLZ",
  gemeindeschluessel: "Gemeindeschlüssel",
  gewerbe_art: "Gewerbe Art",
  azr_nummer: "AZR-Nummer",
  iban: "IBAN",
  nachname: "Nachname",
  vorname: "Vorname",
  strassenname: "Straßenname",
  hausnummer: "Hausnummer",
  wohnort: "Wohnort",
  postleitzahl: "Postleitzahl",
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
    return "bg-amber-900/80 text-amber-300 border border-amber-700/60";
  if (u.includes("LEER") || u.includes("PFLICHT") || u.includes("FEHLT"))
    return "bg-orange-900/80 text-orange-300 border border-orange-700/60";
  if (u.includes("STEUER") || u.includes("IBAN"))
    return "bg-purple-900/80 text-purple-300 border border-purple-700/60";
  if (u.includes("DATUM") || u.includes("DATE"))
    return "bg-blue-900/80 text-blue-300 border border-blue-700/60";
  return "bg-red-900/80 text-red-300 border border-red-700/60";
}

// ─────────────────────────────────────────────────────────────────────────────
// CSV export
// ─────────────────────────────────────────────────────────────────────────────

const UNSAFE_RE = /^[=+\-@]/;
function sanitize(v: string) { return UNSAFE_RE.test(v) ? `'${v}` : v; }
function csvEscape(v: string) {
  const s = sanitize(v);
  return s.includes(",") || s.includes('"') || s.includes("\n")
    ? `"${s.replace(/"/g, '""')}"` : s;
}
function exportCsv(report: ValidationReport) {
  const BOM = "﻿";
  const hdr = ["Zeilenindex", "Spaltenname", "Ungültiger_Wert", "Fehlertyp", "Korrekturhinweis"];
  const body = report.errors.map(e => [
    String(e.row_index), e.column_name, e.invalid_value, e.error_type, e.fix_suggestion,
  ]);
  const csv = BOM + [hdr, ...body].map(r => r.map(csvEscape).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
  const a = Object.assign(document.createElement("a"), {
    href: url,
    download: `Korrekturbericht_${report.schema_id}_${new Date().toISOString().slice(0, 10)}.csv`,
  });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tooltip positioning: above cell if space allows, else below; clamped to viewport
// ─────────────────────────────────────────────────────────────────────────────

const TIP_W = 288;
const TIP_H = 150; // generous estimate for variable-length content

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

interface TooltipState    { error: ValidationError; cellRect: DOMRect; }
interface HeaderTipState { col: string; rect: DOMRect; }
interface Props          { report: ValidationReport; originalFile: File | null; }

// ─────────────────────────────────────────────────────────────────────────────
// Column-header tooltip — shows full name + display_name_short/long
// ─────────────────────────────────────────────────────────────────────────────

function HeaderTip({ col, rect, report }: {
  col: string; rect: DOMRect; report: ValidationReport;
}) {
  const meta  = report.field_meta?.[col];
  const short = meta?.display_name_short || "";
  const long  = meta?.display_name_long  || "";
  return (
    <div
      role="tooltip"
      style={calcTipStyle(rect)}
      className="pointer-events-none rounded-lg border border-slate-600/80 bg-slate-800 p-3
                 shadow-2xl shadow-black/70"
    >
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Spaltenname
      </p>
      <p className="text-xs font-mono text-slate-200 break-all leading-snug">
        {colLabel(col)}
      </p>
      {short && (
        <p className="mt-2 text-xs font-medium text-slate-400">{short}</p>
      )}
      {long && (
        <p className="mt-0.5 text-xs text-slate-500 leading-snug">{long}</p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pagination button — isolated to keep JSX readable
// ─────────────────────────────────────────────────────────────────────────────

function PagBtn({ label, icon, disabled, onClick }: {
  label: string; icon: React.ReactNode; disabled: boolean; onClick: () => void;
}) {
  return (
    <button
      type="button" title={label} aria-label={label} disabled={disabled} onClick={onClick}
      className="flex items-center justify-center rounded border border-slate-600 bg-slate-800 p-1.5
                 text-slate-400 hover:bg-slate-700 hover:text-slate-200
                 disabled:opacity-30 disabled:cursor-not-allowed
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 transition-colors"
    >
      {icon}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function ResultTable({ report }: Props) {
  const [tip,          setTip]          = useState<TooltipState | null>(null);
  const [filterErrors, setFilterErrors] = useState(false);
  const [pageSize,     setPageSize]     = useState<PageSize>(50);
  const [currentPage,  setCurrentPage]  = useState(0);

  const headers = report.headers ?? [];
  const rows    = report.rows    ?? [];

  // "zeile" column is rendered as the sticky row-number gutter, not as a data column
  const hasZeile    = headers.includes("zeile");
  const dataHeaders = useMemo(() => headers.filter(h => h !== "zeile"), [headers]);

  // O(1) error lookup: "1-based-arrayIdx_colNameLower" → ValidationError
  const errMap = useMemo(() => {
    const m: Record<string, ValidationError> = {};
    for (const e of report.errors) {
      if (e.row_index > 0) m[`${e.row_index}_${e.column_name.toLowerCase()}`] = e;
    }
    return m;
  }, [report.errors]);

  // O(1) warning lookup (same key scheme, separate map — never overlaps errMap)
  const warnMap = useMemo(() => {
    const m: Record<string, ValidationError> = {};
    for (const w of (report.warnings ?? [])) {
      if (w.row_index > 0) m[`${w.row_index}_${w.column_name.toLowerCase()}`] = w;
    }
    return m;
  }, [report.warnings]);

  const structErrors = useMemo(
    () => report.errors.filter(e => e.row_index === 0),
    [report.errors]
  );

  // Tag each row with its original array index so error keys stay stable
  // through pagination and filtering
  const rowsWithIdx = useMemo(
    () => rows.map((row, arrayIdx) => ({ row, arrayIdx })),
    [rows]
  );

  const rowHasError = useCallback(
    (arrayIdx: number) => dataHeaders.some(h => `${arrayIdx + 1}_${h}` in errMap),
    [dataHeaders, errMap]
  );

  const filteredRows = useMemo(
    () => filterErrors ? rowsWithIdx.filter(({ arrayIdx }) => rowHasError(arrayIdx)) : rowsWithIdx,
    [rowsWithIdx, filterErrors, rowHasError]
  );

  const errorRowCount = useMemo(
    () => rowsWithIdx.filter(({ arrayIdx }) => rowHasError(arrayIdx)).length,
    [rowsWithIdx, rowHasError]
  );

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const safePage   = Math.min(currentPage, totalPages - 1);
  const pagedRows  = filteredRows.slice(safePage * pageSize, (safePage + 1) * pageSize);

  const onEnter = useCallback(
    (e: React.MouseEvent<HTMLTableCellElement>, err: ValidationError) =>
      setTip({ error: err, cellRect: e.currentTarget.getBoundingClientRect() }),
    []
  );
  const onLeave = useCallback(() => setTip(null), []);

  const [headerTip, setHeaderTip] = useState<HeaderTipState | null>(null);
  const onHeaderEnter = useCallback(
    (e: React.MouseEvent<HTMLTableCellElement>, col: string) =>
      setHeaderTip({ col, rect: e.currentTarget.getBoundingClientRect() }),
    []
  );
  const onHeaderLeave = useCallback(() => setHeaderTip(null), []);

  // ── Double scrollbar sync ─────────────────────────────────────────────────
  // tableWrapperRef  — the real scrollable table container (bottom scrollbar)
  // fakeScrollRef    — the phantom scrollbar strip above the header
  // innerFakeRef     — invisible div inside the phantom; its width = table scrollWidth
  // isSyncing        — guard ref that breaks the mutual scroll-event echo loop
  const tableWrapperRef = useRef<HTMLDivElement>(null);
  const fakeScrollRef   = useRef<HTMLDivElement>(null);
  const innerFakeRef    = useRef<HTMLDivElement>(null);
  const isSyncing       = useRef(false);

  // Keep the phantom inner div's width equal to the table's scrollWidth.
  // Runs after every render that changes columns or visible rows, using rAF
  // so the DOM is fully laid out before we measure scrollWidth.
  useEffect(() => {
    const wrapper = tableWrapperRef.current;
    const inner   = innerFakeRef.current;
    if (!wrapper || !inner) return;

    const sync = () => {
      if (tableWrapperRef.current && innerFakeRef.current) {
        innerFakeRef.current.style.width = `${tableWrapperRef.current.scrollWidth}px`;
      }
    };

    const rafId = requestAnimationFrame(sync);

    // ResizeObserver as a safety net: catches column-count changes that alter
    // the table's minWidth even without explicit dep changes.
    const ro = new ResizeObserver(sync);
    ro.observe(wrapper);

    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, [dataHeaders, pagedRows]);

  // Scroll the real table when the user drags the top phantom scrollbar.
  // rAF reset prevents the mutual echo: fakeScroll → tableScroll → fakeScroll…
  const handleFakeScroll = useCallback(() => {
    if (isSyncing.current) return;
    const fake    = fakeScrollRef.current;
    const wrapper = tableWrapperRef.current;
    if (!fake || !wrapper) return;
    isSyncing.current    = true;
    wrapper.scrollLeft   = fake.scrollLeft;
    requestAnimationFrame(() => { isSyncing.current = false; });
  }, []);

  // Mirror the bottom native scrollbar position up to the phantom strip.
  const handleTableScroll = useCallback(() => {
    if (isSyncing.current) return;
    const fake    = fakeScrollRef.current;
    const wrapper = tableWrapperRef.current;
    if (!fake || !wrapper) return;
    isSyncing.current  = true;
    fake.scrollLeft    = wrapper.scrollLeft;
    requestAnimationFrame(() => { isSyncing.current = false; });
  }, []);

  // ── Guard: all clean ─────────────────────────────────────────────────────
  if (report.error_count === 0 && (report.warning_count ?? 0) === 0) {
    return (
      <div className="mt-6 flex items-center gap-3 rounded-lg border border-emerald-700 bg-emerald-950 px-5 py-4 text-emerald-300">
        <Info className="h-5 w-5 shrink-0" aria-hidden="true" />
        <p className="text-sm font-medium">
          Alle {report.total_rows.toLocaleString("de-DE")} Datensätze sind fehlerfrei. Keine Korrekturen erforderlich.
        </p>
      </div>
    );
  }

  // ── Guard: no grid data (old backend) ───────────────────────────────────
  if (headers.length === 0) {
    return (
      <div className="mt-6 flex items-center justify-between rounded-lg border border-slate-700 bg-slate-900 px-5 py-4 text-sm text-slate-400">
        <span>Keine Vorschaudaten verfügbar (veraltete Backend-Version).</span>
        <button
          onClick={() => exportCsv(report)}
          className="ml-4 text-blue-400 hover:text-blue-300 underline"
        >
          Korrekturbericht exportieren (.csv)
        </button>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <section aria-labelledby="grid-title" className="mt-6">

      {/* ── Top toolbar ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
        <h2 id="grid-title" className="text-base font-semibold text-slate-200">
          Dateivorschau — {report.schema_name}
        </h2>
        <button
          type="button"
          onClick={() => exportCsv(report)}
          className="inline-flex items-center gap-2 rounded-md bg-blue-700 px-4 py-2 text-sm font-medium text-white
                     hover:bg-blue-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 transition-colors"
          aria-label="Korrekturbericht als CSV herunterladen"
        >
          <Download className="h-4 w-4" aria-hidden="true" />
          Korrekturbericht (.csv)
        </button>
      </div>

      {/* ── Structural errors (missing columns) ─────────────────────────── */}
      {structErrors.length > 0 && (
        <div className="mb-3 space-y-2">
          {structErrors.map((e, i) => (
            <div key={i} role="alert"
              className="flex items-start gap-2 rounded-md border border-red-700 bg-red-950 px-4 py-3 text-sm text-red-300">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" aria-hidden="true" />
              <span><strong>{e.column_name}:</strong> {e.fix_suggestion}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Controls bar ────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mb-3 px-1">

        {/* Error-only filter toggle */}
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <button
            type="button"
            role="switch"
            aria-checked={filterErrors}
            onClick={() => { setFilterErrors(v => !v); setCurrentPage(0); }}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                        focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400
                        ${filterErrors ? "bg-red-600" : "bg-slate-600"}`}
          >
            <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform
                              ${filterErrors ? "translate-x-[18px]" : "translate-x-[3px]"}`} />
          </button>
          <span className="flex items-center gap-1.5 text-sm text-slate-300">
            <Filter className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
            Nur Fehlerzeilen
            {filterErrors && (
              <span className="ml-1 rounded border border-red-800/60 bg-red-900/60 px-1.5 py-0.5 text-xs text-red-300">
                {errorRowCount.toLocaleString("de-DE")} Zeilen
              </span>
            )}
          </span>
        </label>

        {/* Page-size selector */}
        <div className="ml-auto flex items-center gap-2">
          <label htmlFor="page-size-select" className="text-xs text-slate-400 whitespace-nowrap">
            Zeilen / Seite:
          </label>
          <select
            id="page-size-select"
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value) as PageSize); setCurrentPage(0); }}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-300
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          >
            {PAGE_SIZES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {/* ── Excel-style grid (double horizontal scrollbar) ─────────────── */}
      {/*
        Outer wrapper provides the visible border + rounded corners.
        overflow-hidden clips child content at the rounded edges.

        Structure:
          [outer border wrapper]
            [phantom top scrollbar] ← fakeScrollRef  (14 px tall, aria-hidden)
              [inner phantom div]   ← innerFakeRef   (width = table scrollWidth)
            [real table container]  ← tableWrapperRef (overflow-x-auto)
              <table>
      */}
      <div className="rounded-lg border border-slate-700 overflow-hidden">

        {/* Phantom top scrollbar strip */}
        <div
          ref={fakeScrollRef}
          onScroll={handleFakeScroll}
          className="overflow-x-auto overflow-y-hidden border-b border-slate-700/60
                     bg-slate-900/60"
          style={{ height: 14 }}
          aria-hidden="true"
        >
          {/* Width is set imperatively by the useEffect above */}
          <div ref={innerFakeRef} style={{ height: 1 }} />
        </div>

        {/* Real table container — carries the bottom (native) scrollbar */}
        <div
          ref={tableWrapperRef}
          onScroll={handleTableScroll}
          className="overflow-x-auto"
        >
        <table
          className="border-collapse text-xs"
          style={{ minWidth: `${dataHeaders.length * 130 + 52}px` }}
          role="grid"
          aria-label={`Dateivorschau: ${report.schema_name}`}
        >
          <thead>

            {/* ── Row 1: Column letters  A  B  C  …  Z  AA  AB … ──────────── */}
            <tr className="border-b border-slate-600 bg-zinc-900">
              {/* Top-left corner (empty) */}
              <th
                scope="col"
                className="sticky left-0 z-20 w-12 min-w-[3rem] border-r border-slate-600 bg-zinc-900 px-2 py-1.5"
                aria-hidden="true"
              />
              {dataHeaders.map((_, i) => (
                <th
                  key={i}
                  scope="col"
                  className="min-w-[130px] whitespace-nowrap border-r border-slate-700/50 px-2 py-1.5
                             text-center font-mono text-[11px] font-medium text-slate-500"
                >
                  {colIndexToLetter(i)}
                </th>
              ))}
            </tr>

            {/* ── Row 2: Column names ─────────────────────────────────────── */}
            <tr className="border-b border-slate-600 bg-slate-800">
              <th
                scope="col"
                className="sticky left-0 z-20 w-12 min-w-[3rem] border-r border-slate-600 bg-slate-800
                           px-2 py-2 text-center text-[11px] font-normal text-slate-500"
                aria-label="Zeilennummer"
              >
                #
              </th>
              {dataHeaders.map(h => (
                <th
                  key={h}
                  scope="col"
                  className="min-w-[130px] cursor-help whitespace-nowrap border-r border-slate-700/50
                             px-3 py-2 text-left font-semibold text-slate-300
                             hover:bg-slate-700/30 transition-colors"
                  onMouseEnter={e => onHeaderEnter(e, h)}
                  onMouseLeave={onHeaderLeave}
                >
                  {truncateLabel(colLabel(h))}
                </th>
              ))}
            </tr>

          </thead>
          <tbody>
            {pagedRows.map(({ row, arrayIdx }) => {
              const rowIdx    = arrayIdx + 1;
              const zeileVal  = hasZeile ? (row["zeile"] || String(rowIdx)) : String(rowIdx);
              const rowHasErr = dataHeaders.some(h => `${rowIdx}_${h}` in errMap);

              return (
                <tr
                  key={arrayIdx}
                  className={`border-b border-slate-700/30 transition-colors
                              ${rowHasErr ? "bg-red-950/[0.07]" : "hover:bg-slate-800/30"}`}
                >
                  {/* ── Sticky row-number cell ─────────────────────────── */}
                  <td className="sticky left-0 z-10 w-12 min-w-[3rem] select-none whitespace-nowrap
                                 border-r border-slate-700 bg-zinc-900
                                 px-2 py-1.5 text-center font-mono text-slate-500">
                    {zeileVal}
                  </td>

                  {/* ── Dynamic data cells ────────────────────────────── */}
                  {dataHeaders.map(h => {
                    const key  = `${rowIdx}_${h}`;
                    const err  = errMap[key];
                    const warn = warnMap[key];
                    const val  = String(row[h] ?? "");

                    if (err) {
                      return (
                        <td
                          key={h}
                          className="min-w-[130px] cursor-help border border-red-500/40
                                     bg-red-950/40 px-3 py-1.5 transition-colors hover:bg-red-900/50"
                          onMouseEnter={e => onEnter(e, err)}
                          onMouseLeave={onLeave}
                          aria-label={`${colLabel(h)}: Fehler — ${err.error_type}`}
                        >
                          {val
                            ? <span className="font-mono text-red-300">{val}</span>
                            : <em className="not-italic text-red-500/70">∅ leer</em>
                          }
                        </td>
                      );
                    }

                    if (warn) {
                      return (
                        <td
                          key={h}
                          className="min-w-[130px] cursor-help border border-amber-700/50
                                     bg-amber-950/40 px-3 py-1.5 transition-colors hover:bg-amber-900/40"
                          onMouseEnter={e => onEnter(e, warn)}
                          onMouseLeave={onLeave}
                          aria-label={`${colLabel(h)}: Hinweis — ${warn.error_type}`}
                        >
                          <em className="not-italic text-amber-300">∅ leer</em>
                        </td>
                      );
                    }

                    return (
                      <td
                        key={h}
                        className="min-w-[130px] whitespace-nowrap border-r border-slate-700/30
                                   px-3 py-1.5 text-slate-300"
                      >
                        {val || <span className="text-slate-600">—</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>{/* end tableWrapperRef */}
      </div>{/* end double scrollbar wrapper */}

      {/* ── Pagination controls ──────────────────────────────────────────── */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1">
        <span className="text-xs text-slate-400">
          {filteredRows.length.toLocaleString("de-DE")} Zeilen
          {filterErrors ? " (nur Fehler)" : ""}
          {" · Seite "}
          <strong className="text-slate-200">{safePage + 1}</strong>
          {" von "}
          <strong className="text-slate-200">{totalPages}</strong>
        </span>

        <div className="flex items-center gap-1">
          <PagBtn
            label="Erste Seite"
            icon={<ChevronsLeft  className="h-4 w-4" />}
            disabled={safePage === 0}
            onClick={() => setCurrentPage(0)}
          />
          <PagBtn
            label="Vorherige Seite"
            icon={<ChevronLeft   className="h-4 w-4" />}
            disabled={safePage === 0}
            onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
          />
          <span className="min-w-[5rem] rounded border border-slate-600 bg-slate-800
                           px-3 py-1.5 text-center text-xs text-slate-200">
            {safePage + 1} / {totalPages}
          </span>
          <PagBtn
            label="Nächste Seite"
            icon={<ChevronRight  className="h-4 w-4" />}
            disabled={safePage >= totalPages - 1}
            onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
          />
          <PagBtn
            label="Letzte Seite"
            icon={<ChevronsRight className="h-4 w-4" />}
            disabled={safePage >= totalPages - 1}
            onClick={() => setCurrentPage(totalPages - 1)}
          />
        </div>
      </div>

      {/* ── Header tooltip portal ───────────────────────────────────────── */}
      {headerTip && createPortal(
        <HeaderTip col={headerTip.col} rect={headerTip.rect} report={report} />,
        document.body
      )}

      {/* ── Cell tooltip portal (fixed, never clipped, smart bounds) ─────── */}
      {tip && createPortal(
        <div
          role="tooltip"
          style={calcTipStyle(tip.cellRect)}
          className="pointer-events-none rounded-lg border border-slate-600/80 bg-slate-800 p-3
                     shadow-2xl shadow-black/70"
        >
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Fehlertyp
          </p>
          <span className={`mb-3 inline-block rounded px-2 py-0.5 text-xs font-medium
                            ${errBadgeClass(tip.error.error_type)}`}>
            {tip.error.error_type}
          </span>
          <p className="mb-1 text-xs font-semibold text-slate-300">Korrekturhinweis</p>
          <p className="text-xs leading-relaxed text-slate-400">{tip.error.fix_suggestion}</p>
        </div>,
        document.body
      )}

    </section>
  );
}
