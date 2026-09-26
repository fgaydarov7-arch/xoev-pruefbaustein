import { useEffect, useState } from "react";
import { ShieldCheck, AlertCircle, Loader2 } from "lucide-react";
import {
  fetchSchemas, fetchFields, validateFile,
  ColumnMapping, FieldDef, SchemaInfo, ValidationReport,
} from "./api";
import { FileUploader } from "./components/FileUploader";
import { StatsCard }    from "./components/StatsCard";
import { ResultTable }  from "./components/ResultTable";

type AppState = "idle" | "loading" | "success" | "error";

export default function App() {
  const [schemas,       setSchemas]       = useState<SchemaInfo[]>([]);
  const [schemaId,      setSchemaId]      = useState<string>("");
  const [selectedFile,  setSelectedFile]  = useState<File | null>(null);
  const [report,        setReport]        = useState<ValidationReport | null>(null);
  const [appState,      setAppState]      = useState<AppState>("idle");
  const [errorMsg,      setErrorMsg]      = useState<string>("");
  const [schemasError,  setSchemasError]  = useState<string>("");
  const [fields,        setFields]        = useState<FieldDef[]>([]);
  const [revalidating,  setRevalidating]  = useState(false);

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

  useEffect(() => {
    if (!schemaId) return;
    fetchFields(schemaId)
      .then(setFields)
      .catch(() => setFields([]));
  }, [schemaId]);

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
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

  async function handleRevalidate(mapping: ColumnMapping) {
    if (!selectedFile || !schemaId) return;
    setRevalidating(true);
    try {
      const result = await validateFile(selectedFile, schemaId, mapping);
      setReport(result);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Fehler bei der Neuvalidierung.");
      setAppState("error");
    } finally {
      setRevalidating(false);
    }
  }

  const isLoading = appState === "loading";
  const canSubmit = !!selectedFile && !!schemaId && !isLoading;

  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#222222] font-sans">

      {/* ── Behörden-Header ─────────────────────────────────────────────────── */}
      <header className="bg-[#003366] text-white">
        <div className="mx-auto max-w-[90%] px-4 sm:px-6 py-4 flex items-center gap-4">
          <ShieldCheck className="h-7 w-7 shrink-0" aria-hidden="true" />
          <div>
            <h1 className="text-lg font-bold leading-tight tracking-wide">
              XÖV Validation Console
            </h1>
            <p className="text-xs text-blue-200 mt-0.5">
              Datenschutzkonforme Offline-Validierung · BSI-Grundschutz · BITV&nbsp;2.0
            </p>
          </div>
        </div>
      </header>
      <div className="h-1 bg-[#005B9A]" aria-hidden="true" />

      <main className="mx-auto max-w-[90%] px-4 sm:px-6 py-8">

        {/* Backend-Verbindungsfehler */}
        {schemasError && (
          <div role="alert"
            className="mb-6 flex items-start gap-3 border-l-4 border-red-600 bg-red-50 px-4 py-3 text-red-800 text-sm">
            <AlertCircle className="h-5 w-5 mt-0.5 shrink-0 text-red-600" aria-hidden="true" />
            <span>{schemasError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} aria-label="Datei-Validierungsformular" noValidate>

          {/* ── Schritt 1: Schema ─────────────────────────────────────────── */}
          <section aria-labelledby="schema-section-title" className="mb-8">
            <h2 id="schema-section-title"
              className="mb-3 pb-1 text-[11px] font-bold uppercase tracking-widest text-[#555555] border-b border-[#D1D5DB]">
              Schritt&nbsp;1 — XÖV-Schema auswählen
            </h2>

            {schemas.length > 0 ? (
              <fieldset>
                <legend className="sr-only">XÖV-Schema</legend>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {schemas.map((s) => (
                    <label key={s.schema_id}
                      className={`flex flex-col gap-1 border-2 p-4 cursor-pointer transition-colors
                        focus-within:outline-none focus-within:ring-2 focus-within:ring-[#FFBF47] focus-within:ring-offset-2
                        ${schemaId === s.schema_id
                          ? "border-[#003366] bg-[#EEF4FA]"
                          : "border-[#D1D5DB] bg-white hover:border-[#005B9A]"
                        }`}>
                      <input type="radio" name="schema" value={s.schema_id}
                        checked={schemaId === s.schema_id}
                        onChange={() => setSchemaId(s.schema_id)}
                        className="sr-only" />
                      <span className={`text-[10px] font-bold uppercase tracking-widest ${
                        schemaId === s.schema_id ? "text-[#003366]" : "text-[#555555]"
                      }`}>
                        {s.xoev_standard} {s.version}
                      </span>
                      <span className="text-sm font-semibold text-[#222222] leading-snug">
                        {s.schema_name}
                      </span>
                      {s.description && (
                        <span className="text-xs text-[#555555] leading-snug">{s.description}</span>
                      )}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : (
              !schemasError && (
                <div className="flex items-center gap-2 text-[#555555] text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Schemata werden geladen…
                </div>
              )
            )}
          </section>

          {/* ── Schritt 2: Datei ──────────────────────────────────────────── */}
          <section aria-labelledby="upload-section-title" className="mb-6">
            <h2 id="upload-section-title"
              className="mb-3 pb-1 text-[11px] font-bold uppercase tracking-widest text-[#555555] border-b border-[#D1D5DB]">
              Schritt&nbsp;2 — Datei hochladen
            </h2>
            <FileUploader onFileSelect={setSelectedFile} disabled={isLoading} />
          </section>

          <div className="flex items-center gap-4">
            <button type="submit" disabled={!canSubmit}
              className="inline-flex items-center gap-2 bg-[#003366] px-6 py-2.5 text-sm
                         font-semibold text-white hover:bg-[#005B9A] transition-colors
                         focus:outline-none focus:ring-2 focus:ring-[#FFBF47] focus:ring-offset-2
                         disabled:opacity-40 disabled:cursor-not-allowed">
              {isLoading ? (
                <><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />Validierung läuft…</>
              ) : (
                <><ShieldCheck className="h-4 w-4" aria-hidden="true" />Datei prüfen</>
              )}
            </button>
            {isLoading && (
              <p className="text-sm text-[#555555]" role="status" aria-live="polite">
                Datei wird in-memory verarbeitet. Bitte warten…
              </p>
            )}
          </div>
        </form>

        {/* Validierungsfehler */}
        {appState === "error" && (
          <div role="alert" aria-live="assertive"
            className="mt-6 flex items-start gap-3 border-l-4 border-red-600 bg-red-50 px-4 py-3 text-red-800 text-sm">
            <AlertCircle className="h-5 w-5 mt-0.5 shrink-0 text-red-600" aria-hidden="true" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* ── Schritt 3: Ergebnis ───────────────────────────────────────── */}
        {appState === "success" && report && (
          <section aria-label="Validierungsergebnis" className="mt-10">
            <h2 className="mb-3 pb-1 text-[11px] font-bold uppercase tracking-widest text-[#555555] border-b border-[#D1D5DB]">
              Schritt&nbsp;3 — Ergebnis
            </h2>
            <StatsCard
              totalRows={report.total_rows}
              errorCount={report.error_count}
              warningCount={report.warning_count ?? 0}
              successRate={report.success_rate}
            />
            <ResultTable
              report={report}
              originalFile={selectedFile}
              fields={fields}
              onRevalidate={handleRevalidate}
              revalidating={revalidating}
            />
          </section>
        )}
      </main>

      <footer className="mt-16 border-t border-[#D1D5DB] bg-[#003366] py-4">
        <p className="text-center text-xs text-blue-200">
          XÖV-Prüfbaustein — Lizenziert unter EUPL&nbsp;1.2 ·
          Keine personenbezogenen Daten werden gespeichert · Vollständig offline-fähig
        </p>
      </footer>
    </div>
  );
}
