import { CheckCircle, AlertTriangle, FileText, Info } from "lucide-react";

interface Props {
  totalRows: number;
  errorCount: number;
  warningCount: number;
  successRate: number;
}

export function StatsCard({ totalRows, errorCount, warningCount, successRate }: Props) {
  const hasErrors   = errorCount   > 0;
  const hasWarnings = warningCount > 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 my-6">
      {/* Zeilen Gesamt */}
      <div className="flex items-center gap-4 rounded-lg border border-slate-700 bg-slate-800 px-5 py-4">
        <FileText className="h-8 w-8 text-blue-400 shrink-0" aria-hidden="true" />
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
            Zeilen Gesamt
          </p>
          <p className="mt-1 text-2xl font-bold text-slate-100">
            {totalRows.toLocaleString("de-DE")}
          </p>
        </div>
      </div>

      {/* Gefundene Fehler */}
      <div
        className={`flex items-center gap-4 rounded-lg border px-5 py-4 ${
          hasErrors
            ? "border-red-700 bg-red-950"
            : "border-slate-700 bg-slate-800"
        }`}
        role={hasErrors ? "alert" : undefined}
        aria-live="polite"
      >
        <AlertTriangle
          className={`h-8 w-8 shrink-0 ${hasErrors ? "text-red-400" : "text-slate-500"}`}
          aria-hidden="true"
        />
        <div>
          <p
            className={`text-xs font-medium uppercase tracking-wider ${
              hasErrors ? "text-red-400" : "text-slate-400"
            }`}
          >
            Gefundene Fehler
          </p>
          <p
            className={`mt-1 text-2xl font-bold ${
              hasErrors ? "text-red-300" : "text-slate-100"
            }`}
          >
            {errorCount.toLocaleString("de-DE")}
          </p>
        </div>
      </div>

      {/* Gefundene Hinweise */}
      <div
        className={`flex items-center gap-4 rounded-lg border px-5 py-4 ${
          hasWarnings
            ? "border-amber-700 bg-amber-950"
            : "border-slate-700 bg-slate-800"
        }`}
        aria-live="polite"
      >
        <Info
          className={`h-8 w-8 shrink-0 ${hasWarnings ? "text-amber-400" : "text-slate-500"}`}
          aria-hidden="true"
        />
        <div>
          <p
            className={`text-xs font-medium uppercase tracking-wider ${
              hasWarnings ? "text-amber-400" : "text-slate-400"
            }`}
          >
            Gefundene Hinweise
          </p>
          <p
            className={`mt-1 text-2xl font-bold ${
              hasWarnings ? "text-amber-300" : "text-slate-100"
            }`}
          >
            {warningCount.toLocaleString("de-DE")}
          </p>
        </div>
      </div>

      {/* Erfolgsquote */}
      <div className="flex items-center gap-4 rounded-lg border border-slate-700 bg-slate-800 px-5 py-4">
        <CheckCircle
          className={`h-8 w-8 shrink-0 ${
            successRate >= 100 ? "text-emerald-400" : successRate >= 80 ? "text-yellow-400" : "text-red-400"
          }`}
          aria-hidden="true"
        />
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
            Erfolgsquote
          </p>
          <p
            className={`mt-1 text-2xl font-bold ${
              successRate >= 100
                ? "text-emerald-300"
                : successRate >= 80
                ? "text-yellow-300"
                : "text-red-300"
            }`}
          >
            {successRate.toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %
          </p>
        </div>
      </div>
    </div>
  );
}
