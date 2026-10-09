import { beforeEach, expect, it, vi } from 'vitest';
import client from './client';
import { createD4TextPreview, getD4PreviewAvailability, getD4PreviewVersion, parseD4TextPreview } from './capaD4TextPreview';
vi.mock('./client', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const id = '00000000-0000-4000-8000-000000000001';
function preview() {
  const now = Date.now();
  return { report_id: id, rule_version: 'capa.d4.redaction.v1', source_version: 'a'.repeat(64),
    generated_at: new Date(now).toISOString(), expires_at: new Date(now + 30000).toISOString(),
    data_class: 'restricted', projection: 'redaction_candidate', declassification_status: 'not_approved',
    external_delivery_allowed: false, fields: [{ field: 'd4_root_cause', verification_id: null,
      redacted_text: '受限技术叙述', source_status: 'unverified', source_ref: null, match_counts: {} }] };
}
beforeEach(() => vi.clearAllMocks());
it('parses only the fixed target and restricted candidate contract', () => {
  const value = preview();
  expect(parseD4TextPreview(value, id)).toEqual(value);
  for (const change of [{ data_class: 'internal' }, { external_delivery_allowed: 0 },
    { external_delivery_allowed: true }, { declassification_status: 'approved' }, { raw_text: 'SECRET' },
    { source_version: 'short' }, { expires_at: value.generated_at }, { report_id: 'not-id' }]) {
    expect(() => parseD4TextPreview({ ...value, ...change }, id)).toThrow('PREVIEW_RESPONSE_INVALID');
  }
  for (const change of [{ match_counts: { secret_word: 1 } }, { match_counts: { literal: true } },
    { field: 'd2_description' }, { raw_text: 'SECRET' }, { source_status: 'validated_reference' }]) {
    expect(() => parseD4TextPreview({ ...value, fields: [{ ...value.fields[0], ...change }] }, id)).toThrow('PREVIEW_RESPONSE_INVALID');
  }
});
it('uses exact user-only endpoints and an abort signal without authority fields', async () => {
  const body = { replacement_terms: ['private'] };
  const signal = new AbortController().signal;
  vi.mocked(client.post).mockResolvedValue({ data: preview() });
  expect((await createD4TextPreview(id, body, signal)).report_id).toBe(id);
  expect(client.post).toHaveBeenCalledWith(`/capa/${id}/d4-text-preview`, body, { signal });
  vi.mocked(client.get).mockResolvedValueOnce({ data: { enabled: true } }).mockResolvedValueOnce({ data: {
    report_id: id, rule_version: 'capa.d4.redaction.v1', source_version: 'a'.repeat(64) } });
  expect(await getD4PreviewAvailability(id, signal)).toEqual({ enabled: true });
  expect((await getD4PreviewVersion(id, signal)).source_version).toBe('a'.repeat(64));
});
