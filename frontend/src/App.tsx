import { useEffect, useState } from "react";
import { ShieldCheck, AlertCircle, Loader2 } from "lucide-react";
import { fetchSchemas, validateFile, SchemaInfo, ValidationReport } from "./api";
import { FileUploader } from "./components/FileUploader";
import { StatsCard } from "./components/StatsCard";
import { ResultTable } from "./components/ResultTable";

type AppState = "idle" | "loading" | "success" | "error";

export default function App() {
  const [schemas, setSchemas] = useState<SchemaInfo[]>([]);
  const [schemaId, setSchemaId] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [appState, setAppState] = useState<AppState>("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [schemasError, setSchemasError] = useState<string>("");

  useEffect(() => {
    fetchSchemas()
      .then((data) => {
        setSchemas(data);
        if (data.length > 0) setSchemaId(data[0].schema_id);
      })
      .catch(() => {
        setSchemasError(
          "Verbindung zum Backend nicht möglich. Bitte stellen Sie sicher, dass der Python-Server auf Port 8000 läuft."
        );
      });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile || !schemaId) return;

    setAppState("loading");
    setReport(null);
    setErrorMsg("");

    try {
      const result = await validateFile(selectedFile, schemaId);
      setReport(result);
      setAppState("success");
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Unbekannter Fehler.");
      setAppState("error");
    }
  }

  const isLoading = appState === "loading";
  const canSubmit = !!selectedFile && !!schemaId && !isLoading;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900 shadow-md">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 py-4 flex items-center gap-3">
          <ShieldCheck className="h-7 w-7 text-blue-400 shrink-0" aria-hidden="true" />
          <div>
            <h1 className="text-lg font-bold leading-tight text-slate-100">
              XÖV-Prüfbaustein
            </h1>
            <p className="text-xs text-slate-400">
              Datenschutzkonforme Offline-Validierung für kommunale Register &middot; BSI-Grundschutz konform
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 sm:px-6 py-8">
        {/* Backend connection error */}
        {schemasError && (
          <div
            role="alert"
            className="mb-6 flex items-start gap-3 rounded-lg border border-red-700 bg-red-950 px-4 py-3 text-red-300 text-sm"
          >
            <AlertCircle className="h-5 w-5 mt-0.5 shrink-0" aria-hidden="true" />
            <span>{schemasError}</span>
          </div>
        )}

        {/* Upload form */}
        <form
          onSubmit={handleSubmit}
          aria-label="Datei-Validierungsformular"
          noValidate
        >
          <section aria-labelledby="upload-section-title">
            <h2
              id="upload-section-title"
              className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400"
            >
              1. XÖV-Schema auswählen
            </h2>

            {schemas.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
                {schemas.map((s) => (
                  <label
                    key={s.schema_id}
                    className={`flex flex-col gap-1 rounded-lg border p-4 cursor-pointer transition-colors ${
                      schemaId === s.schema_id
                        ? "border-blue-500 bg-blue-950/60"
                        : "border-slate-700 bg-slate-800 hover:border-blue-600"
                    }`}
                  >
                    <input
                      type="radio"
                      name="schema"
                      value={s.schema_id}
                      checked={schemaId === s.schema_id}
                      onChange={() => setSchemaId(s.schema_id)}
                      className="sr-only"
                    />
                    <span className="text-xs font-bold uppercase tracking-wider text-blue-400">
                      {s.xoev_standard} {s.version}
                    </span>
                    <span className="text-sm font-medium text-slate-200 leading-snug">
                      {s.schema_name}
                    </span>
                    {s.description && (
                      <span className="text-xs text-slate-400 leading-snug">
                        {s.description}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            ) : (
              !schemasError && (
                <div className="flex items-center gap-2 text-slate-400 text-sm mb-6">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Schemata werden geladen…
                </div>
              )
            )}

            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
              2. Datei hochladen
            </h2>
            <FileUploader onFileSelect={setSelectedFile} disabled={isLoading} />
          </section>

          {/* Submit */}
          <div className="mt-6 flex items-center gap-4">
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white shadow hover:bg-blue-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Validierung läuft…
                </>
              ) : (
                <>
                  <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                  Datei prüfen
                </>
              )}
            </button>
            {isLoading && (
              <p className="text-sm text-slate-400" role="status" aria-live="polite">
                Datei wird in-memory verarbeitet. Bitte warten…
              </p>
            )}
          </div>
        </form>

        {/* API error */}
        {appState === "error" && (
          <div
            role="alert"
            aria-live="assertive"
            className="mt-6 flex items-start gap-3 rounded-lg border border-red-700 bg-red-950 px-4 py-3 text-red-300 text-sm"
          >
            <AlertCircle className="h-5 w-5 mt-0.5 shrink-0" aria-hidden="true" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Results */}
        {appState === "success" && report && (
          <section aria-label="Validierungsergebnis" className="mt-8">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-400">
              3. Ergebnis
            </h2>
            <StatsCard
              totalRows={report.total_rows}
              errorCount={report.error_count}
              successRate={report.success_rate}
            />
            <ResultTable report={report} originalFile={selectedFile} />
          </section>
        )}
      </main>

      <footer className="mt-16 border-t border-slate-800 bg-slate-900 py-4">
        <p className="text-center text-xs text-slate-600">
          XÖV-Prüfbaustein &mdash; Lizenziert unter EUPL 1.2 &middot; Keine personenbezogenen Daten werden gespeichert &middot; Vollständig offline-fähig
        </p>
      </footer>
    </div>
  );
}
