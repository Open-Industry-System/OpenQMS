import client from './client';
import type { D4CountKind, D4PreviewField, D4PreviewRequest, D4PreviewVersion, D4TextPreview } from '../types/capaD4TextPreview';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const digest = /^[0-9a-f]{64}$/;
const categories = new Set(['literal', 'credential', 'url', 'email', 'id_number', 'mobile', 'phone']);
function requireValue(condition: unknown): asserts condition {
  if (!condition) throw new Error('PREVIEW_RESPONSE_INVALID');
}
function record(value: unknown, keys: string[]): Record<string, unknown> {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value));
  const object = value as Record<string, unknown>;
  requireValue(Object.keys(object).length === keys.length && keys.every(key => Object.prototype.hasOwnProperty.call(object, key)));
  return object;
}
function identifier(value: unknown): string {
  requireValue(typeof value === 'string' && uuid.test(value));
  return value;
}
function fingerprint(value: unknown): string {
  requireValue(typeof value === 'string' && digest.test(value));
  return value;
}
function version(value: Record<string, unknown>, reportId: string): D4PreviewVersion {
  requireValue(identifier(value.report_id) === reportId && value.rule_version === 'capa.d4.redaction.v1');
  return { report_id: reportId, rule_version: 'capa.d4.redaction.v1', source_version: fingerprint(value.source_version) };
}
function field(value: unknown): D4PreviewField {
  const row = record(value, ['field', 'verification_id', 'redacted_text', 'source_status', 'source_ref', 'match_counts']);
  requireValue(['d4_root_cause', 'root_cause_text', 'result'].includes(String(row.field)));
  requireValue(row.redacted_text === null || typeof row.redacted_text === 'string');
  requireValue((row.field === 'd4_root_cause') === (row.verification_id === null));
  const verification = row.verification_id === null ? null : identifier(row.verification_id);
  requireValue(row.source_status === 'unverified' || row.source_status === 'validated_reference');
  requireValue((row.source_status === 'validated_reference') === (row.source_ref !== null));
  let source: D4PreviewField['source_ref'] = null;
  if (row.source_ref !== null) {
    const ref = record(row.source_ref, ['owner', 'object_id', 'node_id', 'version']);
    requireValue(ref.owner === 'fmea' && typeof ref.node_id === 'string' && ref.node_id.length >= 1 && ref.node_id.length <= 128);
    source = { owner: 'fmea', object_id: identifier(ref.object_id), node_id: ref.node_id, version: fingerprint(ref.version) };
  }
  requireValue(row.match_counts !== null && typeof row.match_counts === 'object' && !Array.isArray(row.match_counts));
  const counts: Partial<Record<D4CountKind, number>> = {};
  for (const [key, count] of Object.entries(row.match_counts)) {
    requireValue(categories.has(key) && typeof count === 'number' && Number.isSafeInteger(count) && count >= 0);
    counts[key as D4CountKind] = count;
  }
  return { field: row.field as D4PreviewField['field'], verification_id: verification,
    redacted_text: row.redacted_text as string | null, source_status: row.source_status, source_ref: source, match_counts: counts };
}
export function parseD4TextPreview(value: unknown, reportId: string): D4TextPreview {
  const row = record(value, ['report_id', 'rule_version', 'source_version', 'generated_at', 'expires_at', 'data_class',
    'projection', 'declassification_status', 'external_delivery_allowed', 'fields']);
  const header = version(row, reportId);
  requireValue(row.data_class === 'restricted' && row.projection === 'redaction_candidate'
    && row.declassification_status === 'not_approved' && row.external_delivery_allowed === false);
  requireValue(typeof row.generated_at === 'string' && typeof row.expires_at === 'string');
  const generated = Date.parse(row.generated_at), expires = Date.parse(row.expires_at);
  requireValue(Number.isFinite(generated) && Number.isFinite(expires) && expires - generated === 30000);
  requireValue(Array.isArray(row.fields) && row.fields.length >= 1 && row.fields.length <= 401);
  const fields = row.fields.map(field);
  const seen = new Set(fields.map(item => `${item.verification_id}:${item.field}`));
  requireValue(seen.size === fields.length && fields.filter(item => item.field === 'd4_root_cause').length === 1);
  return { ...header, generated_at: row.generated_at, expires_at: row.expires_at, data_class: 'restricted',
    projection: 'redaction_candidate', declassification_status: 'not_approved', external_delivery_allowed: false, fields };
}
function base(reportId: string) { return `/capa/${identifier(reportId)}/d4-text-preview`; }
export async function getD4PreviewAvailability(reportId: string, signal?: AbortSignal): Promise<{ enabled: true }> {
  const row = record((await client.get(base(reportId) + '/availability', { signal })).data, ['enabled']);
  requireValue(row.enabled === true);
  return { enabled: true };
}
export async function getD4PreviewVersion(reportId: string, signal?: AbortSignal): Promise<D4PreviewVersion> {
  return version(record((await client.get(base(reportId) + '/version', { signal })).data,
    ['report_id', 'rule_version', 'source_version']), reportId);
}
export async function createD4TextPreview(reportId: string, body: D4PreviewRequest, signal?: AbortSignal): Promise<D4TextPreview> {
  return parseD4TextPreview((await client.post(base(reportId), body, { signal })).data, reportId);
}
