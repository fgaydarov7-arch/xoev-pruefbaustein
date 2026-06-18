import { useRef, useState, DragEvent, KeyboardEvent, ChangeEvent } from "react";
import { UploadCloud } from "lucide-react";

interface Props {
  onFileSelect: (file: File) => void;
  disabled?: boolean;
}

export function FileUploader({ onFileSelect, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const ACCEPTED = ".csv,.xlsx,.xls";

  function handleFile(file: File | undefined) {
    if (!file) return;
    setFileName(file.name);
    onFileSelect(file);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    handleFile(e.dataTransfer.files?.[0]);
  }

  function onDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }

  function onDragLeave() {
    setIsDragging(false);
  }

  function onChange(e: ChangeEvent<HTMLInputElement>) {
    handleFile(e.target.files?.[0]);
    // Reset so the same file can be re-selected after clearing
    e.target.value = "";
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      inputRef.current?.click();
    }
  }

  const borderClass = isDragging
    ? "border-blue-400 bg-blue-950"
    : "border-slate-600 bg-slate-800 hover:border-blue-500 hover:bg-slate-750";

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Datei per Drag-and-drop hochladen oder klicken zum Auswählen (CSV oder Excel, max. 50 MB)"
      aria-disabled={disabled}
      className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 text-center transition-colors duration-150 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${borderClass} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onKeyDown={onKeyDown}
      onClick={() => !disabled && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={onChange}
        disabled={disabled}
      />
      <UploadCloud
        className={`h-12 w-12 mb-3 ${isDragging ? "text-blue-300" : "text-slate-500"}`}
        aria-hidden="true"
      />
      {fileName ? (
        <>
          <p className="text-sm font-semibold text-blue-300">{fileName}</p>
          <p className="mt-1 text-xs text-slate-400">
            Klicken oder Datei ziehen, um die Datei zu ersetzen
          </p>
        </>
      ) : (
        <>
          <p className="text-sm font-medium text-slate-300">
            CSV- oder Excel-Datei hier ablegen
          </p>
          <p className="mt-1 text-xs text-slate-500">
            oder klicken zur Dateiauswahl &mdash; max. 50 MB
          </p>
        </>
      )}
    </div>
  );
}
