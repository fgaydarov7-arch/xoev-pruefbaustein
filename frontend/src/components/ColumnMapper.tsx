import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Loader2,
  Search,
  SkipForward,
  X,
} from "lucide-react";
import { ColumnMapping, FieldDef } from "../api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ColState {
  fileCol:     string;
  selectedKey: string | null;
  autoMatched: boolean;
}

interface OpenDropdown {
  colIdx: number;
  rect:   DOMRect;
  query:  string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function autoMatch(fileCol: string, fields: FieldDef[]): string | null {
  const needle = fileCol.toLowerCase().trim();
  const byKey  = fields.find(f => f.key.toLowerCase() === needle);
  if (byKey) return byKey.key;
  // Strip underscores/hyphens and compare
  const stripped = needle.replace(/[-_\s]/g, "");
  const byStrip  = fields.find(f => f.key.toLowerCase().replace(/[-_\s]/g, "") === stripped);
  return byStrip?.key ?? null;
}

function filterFields(fields: FieldDef[], query: string): FieldDef[] {
  if (!query.trim()) return fields.slice(0, 60);
  const q = query.toLowerCase();
  return fields
    .filter(f => f.key.toLowerCase().includes(q) || f.label.toLowerCase().includes(q))
    .slice(0, 100);
}

// ── Portal dropdown ───────────────────────────────────────────────────────────

interface DropdownPortalProps {
  open:        OpenDropdown | null;
  fields:      FieldDef[];
  colStates:   ColState[];
  onSelect:    (colIdx: number, key: string | null) => void;
  onQueryChange: (q: string) => void;
  onClose:     () => void;
}

function DropdownPortal({
  open, fields, colStates, onSelect, onQueryChange, onClose,
}: DropdownPortalProps) {
  const inputRef    = useRef<HTMLInputElement>(null);
  const listRef     = useRef<HTMLUListElement>(null);
  const [hiIdx, setHiIdx] = useState(0);

  const filtered = useMemo(
    () => (open ? filterFields(fields, open.query) : []),
    [fields, open?.query],
  );

  // Reset highlight when filter changes
  useEffect(() => { setHiIdx(0); }, [filtered]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 20);
  }, [open?.colIdx]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!listRef.current?.contains(target) && !inputRef.current?.contains(target)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onClose]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setHiIdx(i => Math.min(i + 1, filtered.length));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHiIdx(i => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (open) {
          if (hiIdx === 0) onSelect(open.colIdx, null);
          else onSelect(open.colIdx, filtered[hiIdx - 1]?.key ?? null);
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, filtered, hiIdx, onClose, onSelect]);

  if (!open) return null;

  // Position: below the trigger; flip up if too close to viewport bottom
  const DROPDOWN_H = 320;
  const spaceBelow  = window.innerHeight - open.rect.bottom;
  const top = spaceBelow > DROPDOWN_H
    ? open.rect.bottom + 4
    : open.rect.top - DROPDOWN_H - 4;
  const left  = Math.min(open.rect.left, window.innerWidth - 320 - 8);
  const width = Math.max(open.rect.width, 320);

  const currentKey = colStates[open.colIdx]?.selectedKey;

  return createPortal(
    <div
      style={{ position: "fixed", top, left, width, zIndex: 9999 }}
      className="flex flex-col rounded-lg border border-slate-600 bg-slate-800 shadow-2xl"
    >
      {/* Search input */}
      <div className="flex items-center gap-2 border-b border-slate-700 px-3 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          value={open.query}
          onChange={e => { onQueryChange(e.target.value); setHiIdx(0); }}
          placeholder="Feld suchen…"
          className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-500 outline-none"
          aria-label="Feld suchen"
          aria-autocomplete="list"
        />
        {open.query && (
          <button
            type="button"
            onClick={() => { onQueryChange(""); inputRef.current?.focus(); }}
            className="text-slate-500 hover:text-slate-300"
            aria-label="Suche löschen"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Options list */}
      <ul
        ref={listRef}
        role="listbox"
        style={{ maxHeight: DROPDOWN_H - 44, overflowY: "auto" }}
        className="py-1 text-sm"
      >
        {/* Skip / clear option */}
        <li
          role="option"
          aria-selected={currentKey === null}
          onClick={() => onSelect(open.colIdx, null)}
          className={`flex cursor-pointer items-center gap-2 px-3 py-2 transition-colors
            ${hiIdx === 0
              ? "bg-slate-700 text-slate-200"
              : "text-slate-400 hover:bg-slate-700/60"}`}
        >
          <SkipForward className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="italic">— Spalte überspringen —</span>
          {currentKey === null && <Check className="ml-auto h-3.5 w-3.5 text-slate-400" />}
        </li>

        {filtered.length === 0 && (
          <li className="px-3 py-3 text-center text-slate-500">
            Keine Felder gefunden.
          </li>
        )}

        {filtered.map((f, i) => {
          const idx       = i + 1;
          const isActive  = f.key === currentKey;
          const isHi      = idx === hiIdx;
          return (
            <li
              key={f.key}
              role="option"
              aria-selected={isActive}
              onClick={() => onSelect(open.colIdx, f.key)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-2 transition-colors
                ${isHi
                  ? "bg-blue-700 text-white"
                  : isActive
                    ? "bg-blue-950/60 text-blue-300"
                    : "text-slate-300 hover:bg-slate-700/60"}`}
            >
              <span className="flex-1 min-w-0 truncate">{f.label}</span>
              {isActive && <Check className="h-3.5 w-3.5 shrink-0 text-blue-400" aria-hidden="true" />}
            </li>
          );
        })}
      </ul>

      {/* Footer: count */}
      <div className="border-t border-slate-700 px-3 py-1.5 text-right text-xs text-slate-500">
        {open.query
          ? `${filtered.length} Treffer`
          : `${fields.length} Felder verfügbar`}
      </div>
    </div>,
    document.body,
  );
}

// ── ColumnMapper (main export) ────────────────────────────────────────────────

interface Props {
  fileHeaders: string[];
  fields:      FieldDef[];
  schemaName:  string;
  loading:     boolean;
  onConfirm:   (mapping: ColumnMapping) => void;
  onCancel:    () => void;
}

export function ColumnMapper({
  fileHeaders, fields, schemaName, loading, onConfirm, onCancel,
}: Props) {
  // One state entry per file column
  const [cols, setCols] = useState<ColState[]>(() =>
    fileHeaders.map(fc => {
      const matchedKey = autoMatch(fc, fields);
      return { fileCol: fc, selectedKey: matchedKey, autoMatched: matchedKey !== null };
    }),
  );
  const [openDrop, setOpenDrop] = useState<OpenDropdown | null>(null);
  const triggerRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const matchedCount  = cols.filter(c => c.selectedKey !== null).length;
  const unmatchedCols = cols.filter(c => c.selectedKey === null);

  const openDropdown = useCallback((colIdx: number) => {
    const el = triggerRefs.current[colIdx];
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setOpenDrop(prev =>
      prev?.colIdx === colIdx ? null : { colIdx, rect, query: "" },
    );
  }, []);

  const handleSelect = useCallback((colIdx: number, key: string | null) => {
    setCols(prev => {
      const next = [...prev];
      next[colIdx] = { ...next[colIdx], selectedKey: key, autoMatched: false };
      return next;
    });
    setOpenDrop(null);
  }, []);

  const handleQueryChange = useCallback((q: string) => {
    setOpenDrop(prev => prev ? { ...prev, query: q } : prev);
  }, []);

  // Update trigger rect on scroll/resize while dropdown is open
  useEffect(() => {
    if (!openDrop) return;
    const update = () => {
      const el = triggerRefs.current[openDrop.colIdx];
      if (el) setOpenDrop(prev => prev ? { ...prev, rect: el.getBoundingClientRect() } : prev);
    };
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [openDrop?.colIdx]);

  function handleConfirm() {
    const mapping: ColumnMapping = {};
    for (const col of cols) {
      mapping[col.fileCol] = col.selectedKey;
    }
    onConfirm(mapping);
  }

  const fieldByKey = useMemo(() => {
    const m: Record<string, FieldDef> = {};
    for (const f of fields) m[f.key] = f;
    return m;
  }, [fields]);

  return (
    <>
      <DropdownPortal
        open={openDrop}
        fields={fields}
        colStates={cols}
        onSelect={handleSelect}
        onQueryChange={handleQueryChange}
        onClose={() => setOpenDrop(null)}
      />

      <div className="mt-6 rounded-xl border border-slate-700 bg-slate-900 shadow-lg">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700 px-5 py-4">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              Spalten-Zuordnung
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Protokoll: <span className="text-slate-400">{schemaName}</span>
              &ensp;·&ensp;
              <span className="text-emerald-400">{matchedCount}</span> von{" "}
              <span className="text-slate-300">{cols.length}</span> Spalten zugeordnet
              {unmatchedCols.length > 0 && (
                <span className="text-amber-400">
                  &ensp;·&ensp;{unmatchedCols.length} nicht erkannt
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={loading}
              className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-300
                         hover:border-slate-500 hover:text-slate-100 transition-colors disabled:opacity-40"
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-5 py-2 text-sm
                         font-semibold text-white hover:bg-blue-500 transition-colors
                         focus-visible:ring-2 focus-visible:ring-blue-400 disabled:opacity-40"
            >
              {loading ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Validierung läuft…</>
              ) : (
                <><ArrowRight className="h-4 w-4" /> Validieren</>
              )}
            </button>
          </div>
        </div>

        {/* Notice: unmatched columns */}
        {unmatchedCols.length > 0 && (
          <div className="border-b border-amber-800/40 bg-amber-950/30 px-5 py-2.5 text-xs text-amber-400">
            Nicht erkannte Spalten sind rot markiert. Bitte wählen Sie das entsprechende Protokollfeld aus
            oder überspringen Sie die Spalte.
          </div>
        )}

        {/* Mapping table */}
        <div className="overflow-y-auto" style={{ maxHeight: "60vh" }}>
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-slate-800">
              <tr>
                <th className="w-10 border-b border-slate-700 px-3 py-2.5 text-left text-xs font-semibold text-slate-500">
                  #
                </th>
                <th className="w-48 border-b border-slate-700 px-3 py-2.5 text-left text-xs font-semibold text-slate-400">
                  Spalte im File
                </th>
                <th className="border-b border-slate-700 px-3 py-2.5 text-left text-xs font-semibold text-slate-400">
                  Feld im Protokoll
                </th>
                <th className="w-24 border-b border-slate-700 px-3 py-2.5 text-left text-xs font-semibold text-slate-500">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {cols.map((col, idx) => {
                const isOpen      = openDrop?.colIdx === idx;
                const hasError    = col.selectedKey === null;
                const field       = col.selectedKey ? fieldByKey[col.selectedKey] : null;

                return (
                  <tr
                    key={idx}
                    className={`border-b border-slate-800/60 transition-colors
                      ${isOpen ? "bg-slate-800/80" : "hover:bg-slate-800/40"}`}
                  >
                    {/* Index */}
                    <td className="px-3 py-2.5 text-xs text-slate-600 tabular-nums">
                      {idx + 1}
                    </td>

                    {/* File column name */}
                    <td className="px-3 py-2.5">
                      <span
                        className="inline-block max-w-[180px] truncate rounded bg-slate-800
                                   px-2 py-0.5 font-mono text-xs text-slate-300"
                        title={col.fileCol}
                      >
                        {col.fileCol}
                      </span>
                    </td>

                    {/* Combobox trigger */}
                    <td className="px-3 py-2">
                      <button
                        ref={el => { triggerRefs.current[idx] = el; }}
                        type="button"
                        onClick={() => openDropdown(idx)}
                        aria-haspopup="listbox"
                        aria-expanded={isOpen}
                        className={`flex w-full items-center justify-between gap-2 rounded-md
                                    border px-3 py-1.5 text-left text-sm transition-colors
                                    focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                                    ${hasError
                                      ? "border-red-600/70 bg-red-950/30 text-red-400 hover:border-red-500"
                                      : isOpen
                                        ? "border-blue-500 bg-blue-950/30 text-blue-300"
                                        : "border-slate-600 bg-slate-800/60 text-slate-200 hover:border-slate-500"
                                    }`}
                      >
                        <span className="min-w-0 flex-1 truncate">
                          {field
                            ? field.label
                            : hasError
                              ? "Nicht zugeordnet"
                              : "— Spalte überspringen —"}
                        </span>
                        <ChevronDown
                          className={`h-3.5 w-3.5 shrink-0 transition-transform
                            ${isOpen ? "rotate-180" : ""}`}
                          aria-hidden="true"
                        />
                      </button>
                    </td>

                    {/* Status badge */}
                    <td className="px-3 py-2.5">
                      {field ? (
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5
                                         text-xs font-medium
                                         ${col.autoMatched
                                           ? "bg-emerald-950/60 text-emerald-400"
                                           : "bg-blue-950/60 text-blue-400"}`}>
                          <Check className="h-3 w-3" aria-hidden="true" />
                          {col.autoMatched ? "Erkannt" : "Manuell"}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-red-950/50
                                         px-2 py-0.5 text-xs font-medium text-red-400">
                          <X className="h-3 w-3" aria-hidden="true" />
                          Fehlt
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer summary */}
        <div className="flex items-center justify-between border-t border-slate-700 px-5 py-3">
          <p className="text-xs text-slate-500">
            Übersprungene Spalten werden nicht validiert.
            Zugeordnete Spalten werden gegen die Codeliste des Protokolls geprüft.
          </p>
          <span className="text-xs text-slate-600">
            {cols.length} Spalten gesamt
          </span>
        </div>
      </div>
    </>
  );
}
