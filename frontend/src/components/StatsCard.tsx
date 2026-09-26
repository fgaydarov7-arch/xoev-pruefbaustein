import { CheckCircle, AlertTriangle, FileText, Info } from "lucide-react";

interface Props {
  totalRows:    number;
  errorCount:   number;
  warningCount: number;
  successRate:  number;
}

export function StatsCard({ totalRows, errorCount, warningCount, successRate }: Props) {
  const hasErrors   = errorCount   > 0;
  const hasWarnings = warningCount > 0;
  const isClean     = successRate >= 100;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-[#D1D5DB] border border-[#D1D5DB] mt-4 mb-6"
      role="region" aria-label="Validierungsstatistik">

      {/* Zeilen Gesamt */}
      <div className="flex items-center gap-4 bg-white px-5 py-4">
        <FileText className="h-8 w-8 text-[#005B9A] shrink-0" aria-hidden="true" />
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#555555]">
            Zeilen Gesamt
          </p>
          <p className="mt-1 text-2xl font-bold text-[#222222]">
            {totalRows.toLocaleString("de-DE")}
          </p>
        </div>
      </div>

      {/* Gefundene Fehler */}
      <div
        className={`flex items-center gap-4 px-5 py-4 ${
          hasErrors ? "bg-red-50 border-l-4 border-red-600" : "bg-white"
        }`}
        role={hasErrors ? "alert" : undefined}
        aria-live="polite"
      >
        <AlertTriangle
          className={`h-8 w-8 shrink-0 ${hasErrors ? "text-red-600" : "text-[#555555]"}`}
          aria-hidden="true"
        />
        <div>
          <p className={`text-[10px] font-bold uppercase tracking-widest ${
            hasErrors ? "text-red-800" : "text-[#555555]"
          }`}>
            Gefundene Fehler
          </p>
          <p className={`mt-1 text-2xl font-bold ${hasErrors ? "text-red-800" : "text-[#222222]"}`}>
            {errorCount.toLocaleString("de-DE")}
          </p>
        </div>
      </div>

      {/* Gefundene Hinweise */}
      <div
        className={`flex items-center gap-4 px-5 py-4 ${
          hasWarnings ? "bg-amber-50 border-l-4 border-amber-600" : "bg-white"
        }`}
        aria-live="polite"
      >
        <Info
          className={`h-8 w-8 shrink-0 ${hasWarnings ? "text-amber-600" : "text-[#555555]"}`}
          aria-hidden="true"
        />
        <div>
          <p className={`text-[10px] font-bold uppercase tracking-widest ${
            hasWarnings ? "text-amber-800" : "text-[#555555]"
          }`}>
            Hinweise
          </p>
          <p className={`mt-1 text-2xl font-bold ${hasWarnings ? "text-amber-800" : "text-[#222222]"}`}>
            {warningCount.toLocaleString("de-DE")}
          </p>
        </div>
      </div>

      {/* Erfolgsquote */}
      <div className={`flex items-center gap-4 px-5 py-4 ${
        isClean
          ? "bg-green-50 border-l-4 border-green-600"
          : successRate >= 80
            ? "bg-amber-50 border-l-4 border-amber-600"
            : "bg-red-50 border-l-4 border-red-600"
      }`}>
        <CheckCircle
          className={`h-8 w-8 shrink-0 ${
            isClean ? "text-green-600" : successRate >= 80 ? "text-amber-600" : "text-red-600"
          }`}
          aria-hidden="true"
        />
        <div>
          <p className={`text-[10px] font-bold uppercase tracking-widest ${
            isClean ? "text-green-800" : successRate >= 80 ? "text-amber-800" : "text-red-800"
          }`}>
            Erfolgsquote
          </p>
          <p className={`mt-1 text-2xl font-bold ${
            isClean ? "text-green-800" : successRate >= 80 ? "text-amber-800" : "text-red-800"
          }`}>
            {successRate.toLocaleString("de-DE", {
              minimumFractionDigits: 1,
              maximumFractionDigits: 1,
            })}&nbsp;%
          </p>
        </div>
      </div>
    </div>
  );
}
