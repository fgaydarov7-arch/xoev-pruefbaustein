export interface SchemaInfo {
  schema_id: string;
  schema_name: string;
  version: string;
  xoev_standard: string;
  description?: string;
}

export interface FieldMeta {
  display_name_short: string;
  display_name_long: string;
}

export interface ValidationError {
  row_index: number;
  column_name: string;
  invalid_value: string;
  error_type: string;
  fix_suggestion: string;
}

export interface ValidationReport {
  schema_id: string;
  schema_name: string;
  total_rows: number;
  error_count: number;
  warning_count: number;
  success_rate: number;
  headers: string[];
  rows: Record<string, string>[];
  errors: ValidationError[];
  warnings: ValidationError[];
  field_meta?: Record<string, FieldMeta>;
}

export interface FieldDef {
  key:          string;
  label:        string;
  has_codelist?: boolean;
}

/** Mapping sent to /validate: file column name → schema key (null = skip column) */
export type ColumnMapping = Record<string, string | null>;

const BASE_URL = "http://127.0.0.1:8000";

export async function fetchSchemas(): Promise<SchemaInfo[]> {
  const res = await fetch(`${BASE_URL}/schemas`);
  if (!res.ok) throw new Error(`Schemas konnten nicht geladen werden (HTTP ${res.status}).`);
  return res.json();
}

export async function previewHeaders(file: File): Promise<string[]> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/preview`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Vorschau fehlgeschlagen (HTTP ${res.status}).`);
  }
  const data: { headers: string[] } = await res.json();
  return data.headers;
}

export async function fetchFields(schemaId: string): Promise<FieldDef[]> {
  const res = await fetch(`${BASE_URL}/fields/${encodeURIComponent(schemaId)}`);
  if (!res.ok) throw new Error(`Felder konnten nicht geladen werden (HTTP ${res.status}).`);
  return res.json();
}

export async function validateFile(
  file: File,
  schemaId: string,
  mapping?: ColumnMapping,
): Promise<ValidationReport> {
  const form = new FormData();
  form.append("file", file);
  form.append("schema_id", schemaId);
  if (mapping) form.append("mapping", JSON.stringify(mapping));

  const res = await fetch(`${BASE_URL}/validate`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Serverfehler (HTTP ${res.status}).`);
  }
  return res.json();
}
