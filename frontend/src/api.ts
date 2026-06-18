export interface SchemaInfo {
  schema_id: string;
  schema_name: string;
  version: string;
  xoev_standard: string;
  description?: string;
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
  success_rate: number;
  errors: ValidationError[];
}

const BASE_URL = "http://127.0.0.1:8000";

export async function fetchSchemas(): Promise<SchemaInfo[]> {
  const res = await fetch(`${BASE_URL}/schemas`);
  if (!res.ok) throw new Error(`Schemas konnten nicht geladen werden (HTTP ${res.status}).`);
  return res.json();
}

export async function validateFile(
  file: File,
  schemaId: string
): Promise<ValidationReport> {
  const form = new FormData();
  form.append("file", file);
  form.append("schema_id", schemaId);

  const res = await fetch(`${BASE_URL}/validate`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Serverfehler (HTTP ${res.status}).`);
  }
  return res.json();
}
