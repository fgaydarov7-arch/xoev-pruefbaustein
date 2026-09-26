import { useRef, useState, DragEvent, KeyboardEvent, ChangeEvent } from "react";
import { UploadCloud, FileCheck } from "lucide-react";

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

  function onDragLeave() { setIsDragging(false); }

  function onChange(e: ChangeEvent<HTMLInputElement>) {
    handleFile(e.target.files?.[0]);
    e.target.value = "";
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Datei per Drag-and-drop hochladen oder klicken zum Auswählen (CSV oder Excel, max. 50 MB)"
      aria-disabled={disabled}
      className={`flex flex-col items-center justify-center border-2 border-dashed p-10 text-center
        transition-colors duration-150 cursor-pointer
        focus:outline-none focus:ring-2 focus:ring-[#FFBF47] focus:ring-offset-2
        ${isDragging
          ? "border-[#003366] bg-[#EEF4FA]"
          : "border-[#005B9A] bg-[#F4F6F8] hover:border-[#003366] hover:bg-[#EEF4FA]"
        }
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
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

      {fileName ? (
        <>
          <FileCheck className="h-10 w-10 mb-3 text-[#003366]" aria-hidden="true" />
          <p className="text-sm font-semibold text-[#003366]">{fileName}</p>
          <p className="mt-1 text-xs text-[#555555]">
            Klicken oder Datei ziehen, um die Datei zu ersetzen
          </p>
        </>
      ) : (
        <>
          <UploadCloud
            className={`h-10 w-10 mb-3 ${isDragging ? "text-[#003366]" : "text-[#005B9A]"}`}
            aria-hidden="true"
          />
          <p className="text-sm font-semibold text-[#222222]">
            CSV- oder Excel-Datei hier ablegen
          </p>
          <p className="mt-1 text-xs text-[#555555]">
            oder klicken zur Dateiauswahl &mdash; max. 50&nbsp;MB
          </p>
          <p className="mt-2 font-mono text-[10px] text-[#555555]">.csv · .xlsx · .xls</p>
        </>
      )}
    </div>
  );
}
