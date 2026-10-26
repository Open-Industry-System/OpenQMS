import type { Verification, D7NodeAction } from './index';

export interface OutcomeDocumentRef {
  module: 'fmea' | 'planning';
  object_id: string;
  version_id: string;
  sha256: string;
}
export interface OutcomeDecision {
  action: 'approved' | 'rejected';
  actor_id: string | null;
  operated_at: string;
  audit_id: string;
}
export interface CapaOutcomeReview {
  report_id: string;
  status: string;
  contract: 'capa.outcome-review.v1';
  review_round_id: string | null;
  revision: string;
  binding_status: 'pending' | 'verified' | 'legacy_unversioned' | 'unverifiable';
  core: {
    d4_root_cause: string | null;
    d5_correction: string | null;
    d6_verification: string | null;
    d7_prevention: string | null;
  };
  verifications: Verification[];
  d7_actions: D7NodeAction[];
  documents: OutcomeDocumentRef[];
  decision: OutcomeDecision | null;
  supplement: {
    text: string | null;
    review_scope: 'unreviewed_supplement';
    updated_by: string | null;
    updated_at: string | null;
  };
}

// A partial read must never supply a decision token. These checks describe the response,
// not an authorization policy; current source and decision authority remain server-owned.
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string';
const nullableText = (v: unknown): boolean => v === null || text(v);
const fields = (v: Record<string, unknown>, names: string[], check: (v: unknown) => boolean = text) => names.every(k => check(v[k]));
const hash = (v: unknown) => text(v) && /^[0-9a-f]{64}$/.test(v);
const uuid = (v: unknown) => text(v) && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);

export function isCompleteOutcomeReview(v: unknown, reportId: string, status: string): v is CapaOutcomeReview {
  if (!record(v) || v.report_id !== reportId || v.status !== status || v.contract !== 'capa.outcome-review.v1'
    || !hash(v.revision) || !(v.review_round_id === null || uuid(v.review_round_id))
    || !['pending', 'verified', 'legacy_unversioned', 'unverifiable'].includes(String(v.binding_status))) return false;
  if (!record(v.core) || !fields(v.core, ['d4_root_cause', 'd5_correction', 'd6_verification', 'd7_prevention'], nullableText)) return false;
  if (!Array.isArray(v.verifications) || !v.verifications.every(row => record(row)
    && fields(row, ['verification_id', 'capa_id', 'root_cause_text', 'created_at']) && row.capa_id === reportId
    && (row.method === null || ['measurement', 'observation', 'reproduction'].includes(String(row.method)))
    && ['pending', 'passed', 'failed'].includes(String(row.conclusion)) && typeof row.is_verified === 'boolean'
    && fields(row, ['result', 'verified_by', 'verified_at'], nullableText)
    && Array.isArray(row.evidence_attachments) && row.evidence_attachments.every(record)
    && (row.source_ref === null || record(row.source_ref)))) return false;
  if (!Array.isArray(v.d7_actions) || !v.d7_actions.every(row => record(row)
    && fields(row, ['action_id', 'capa_id', 'action', 'status', 'failure_mode_node_id', 'match_source', 'acted_by', 'acted_at'])
    && row.capa_id === reportId
    && fields(row, ['fmea_id', 'failure_cause_node_id', 'prevention_control_node_id', 'prevention_control_name_before', 'prevention_control_name_after', 'reason'], nullableText))) return false;
  if (!Array.isArray(v.documents) || !v.documents.every(doc => record(doc)
    && ['fmea', 'planning'].includes(String(doc.module)) && uuid(doc.object_id) && uuid(doc.version_id) && hash(doc.sha256))) return false;
  const documents = v.documents;
  const hasFmea = (id: unknown) => documents.some((doc: unknown) => record(doc) && doc.module === 'fmea' && doc.object_id === id);
  if (!v.verifications.every(row => row.source_ref === null || (record(row.source_ref)
    && Object.keys(row.source_ref).length === 2 && uuid(row.source_ref.fmea_id)
    && text(row.source_ref.cause_node_id) && !!row.source_ref.cause_node_id.trim() && hasFmea(row.source_ref.fmea_id)))
    || !v.d7_actions.every(row => row.fmea_id === null || hasFmea(row.fmea_id))) return false;
  if (v.decision !== null && !(record(v.decision) && ['approved', 'rejected'].includes(String(v.decision.action))
    && nullableText(v.decision.actor_id) && fields(v.decision, ['operated_at', 'audit_id']))) return false;
  return record(v.supplement) && v.supplement.review_scope === 'unreviewed_supplement'
    && fields(v.supplement, ['text', 'updated_by', 'updated_at'], nullableText);
}
