import { Download, Info } from "lucide-react";
import { ValidationError, ValidationReport } from "../api";

interface Props {
  report: ValidationReport;
  originalFile: File | null;
}

const DOM_CAP = 500;

const UNSAFE_PREFIX_RE = /^[=+\-@]/;

function sanitizeCsvCell(value: string): string {
  const str = String(value ?? "");
  return UNSAFE_PREFIX_RE.test(str) ? `'${str}` : str;
}

function escapeCsvField(value: string): string {
  const sanitized = sanitizeCsvCell(value);
  if (sanitized.includes(",") || sanitized.includes('"') || sanitized.includes("\n")) {
    return `"${sanitized.replace(/"/g, '""')}"`;
  }
  return sanitized;
}

function exportCsv(report: ValidationReport) {
  const BOM = "﻿";
  const headers = ["Zeilenindex", "Spaltenname", "Ungültiger_Wert", "Fehlertyp", "Korrekturhinweis"];
  const rows = report.errors.map((e) => [
    String(e.row_index),
    e.column_name,
    e.invalid_value,
    e.error_type,
    e.fix_suggestion,
  ]);

  const csvContent =
    BOM +
    [headers, ...rows]
      .map((row) => row.map(escapeCsvField).join(","))
      .join("\r\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `Korrekturbericht_${report.schema_id}_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

const ERROR_TYPE_LABELS: Record<string, string> = {
  PFLICHTFELD_LEER: "Pflichtfeld leer",
  FEHLENDE_PFLICHTSPALTE: "Spalte fehlt",
  UNGUELTIGE_STEUER_ID: "Ungültige Steuer-ID",
  UNGUELTIGE_IBAN: "Ungültige IBAN",
  "UNGÜLTIGES_DATUM": "Ungültiges Datum",
  REGEX_VERLETZUNG: "Format ungültig",
  "UNGÜLTIGER_CODELISTEN_WERT": "Unerlaubter Wert",
};

function badgeClass(errorType: string): string {
  switch (errorType) {
    case "PFLICHTFELD_LEER":
    case "FEHLENDE_PFLICHTSPALTE":
      return "bg-orange-900 text-orange-300 border border-orange-700";
    case "UNGUELTIGE_STEUER_ID":
    case "UNGUELTIGE_IBAN":
      return "bg-purple-900 text-purple-300 border border-purple-700";
    case "UNGÜLTIGES_DATUM":
      return "bg-blue-900 text-blue-300 border border-blue-700";
    default:
      return "bg-red-900 text-red-300 border border-red-700";
  }
}

export function ResultTable({ report }: Props) {
  const visible = report.errors.slice(0, DOM_CAP);
  const overflow = report.error_count - DOM_CAP;

  if (report.error_count === 0) {
    return (
      <div className="mt-6 flex items-center gap-3 rounded-lg border border-emerald-700 bg-emerald-950 px-5 py-4 text-emerald-300">
        <Info className="h-5 w-5 shrink-0" aria-hidden="true" />
        <p className="text-sm font-medium">
          Alle {report.total_rows.toLocaleString("de-DE")} Datensätze sind fehlerfrei. Keine Korrekturen erforderlich.
        </p>
      </div>
    );
  }

  return (
    <section aria-labelledby="fehler-tabelle-titel" className="mt-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
        <h2
          id="fehler-tabelle-titel"
          className="text-base font-semibold text-slate-200"
        >
          Validierungsfehler &mdash; {report.schema_name}
        </h2>
        <button
          type="button"
          onClick={() => exportCsv(report)}
          className="inline-flex items-center gap-2 rounded-md bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 transition-colors"
          aria-label="Korrekturbericht als CSV herunterladen"
        >
          <Download className="h-4 w-4" aria-hidden="true" />
          Korrekturbericht exportieren (.csv)
        </button>
      </div>

      {overflow > 0 && (
        <div
          role="status"
          aria-live="polite"
          className="mb-3 flex items-start gap-2 rounded-md border border-yellow-700 bg-yellow-950 px-4 py-3 text-yellow-300 text-sm"
        >
          <Info className="h-4 w-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            Die Tabelle zeigt die ersten <strong>{DOM_CAP}</strong> Fehlereinträge.{" "}
            Die verbleibenden <strong>{overflow.toLocaleString("de-DE")}</strong> Fehler sind vollständig
            im exportierten CSV-Korrekturbericht enthalten.
          </span>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="min-w-full divide-y divide-slate-700 text-sm" role="table">
          <thead className="bg-slate-800">
            <tr>
              <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400 whitespace-nowrap">
                Zeile
              </th>
              <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400 whitespace-nowrap">
                Spalte
              </th>
              <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Fehlerhafter Wert
              </th>
              <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400 whitespace-nowrap">
                Fehlertyp
              </th>
              <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                Korrekturhinweis
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50 bg-slate-900">
            {visible.map((err: ValidationError, i: number) => (
              <tr
                key={i}
                className="hover:bg-slate-800/60 transition-colors"
              >
                <td className="px-4 py-2.5 text-slate-300 font-mono text-xs whitespace-nowrap">
                  {err.row_index === 0 ? "—" : err.row_index.toLocaleString("de-DE")}
                </td>
                <td className="px-4 py-2.5 text-blue-300 font-medium whitespace-nowrap">
                  {err.column_name}
                </td>
                <td className="px-4 py-2.5 text-red-300 font-mono text-xs max-w-xs truncate" title={err.invalid_value}>
                  {err.invalid_value}
                </td>
                <td className="px-4 py-2.5 whitespace-nowrap">
                  <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${badgeClass(err.error_type)}`}>
                    {ERROR_TYPE_LABELS[err.error_type] ?? err.error_type}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-slate-400 text-xs">
                  {err.fix_suggestion}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
