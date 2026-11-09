export type D4CountKind = 'literal' | 'credential' | 'url' | 'email' | 'id_number' | 'mobile' | 'phone';
export interface D4PreviewField {
  field: 'd4_root_cause' | 'root_cause_text' | 'result';
  verification_id: string | null;
  redacted_text: string | null;
  source_status: 'unverified' | 'validated_reference';
  source_ref: { owner: 'fmea'; object_id: string; node_id: string; version: string } | null;
  match_counts: Partial<Record<D4CountKind, number>>;
}
export interface D4PreviewVersion {
  report_id: string;
  rule_version: 'capa.d4.redaction.v1';
  source_version: string;
}
export interface D4TextPreview extends D4PreviewVersion {
  generated_at: string;
  expires_at: string;
  data_class: 'restricted';
  projection: 'redaction_candidate';
  declassification_status: 'not_approved';
  external_delivery_allowed: false;
  fields: D4PreviewField[];
}
export interface D4PreviewRequest { replacement_terms: string[] }
