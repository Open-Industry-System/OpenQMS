import client from './client';
import type {
  AqlProfile,
  AqlRecommendation,
  AqlQualitySnapshot,
  AqlConfig,
  AqlPreviewResult,
} from '../types';

// ── Profile ──

export async function listAqlProfiles(params?: {
  state?: string;
  supplier_id?: string;
  product_line_code?: string;
  page?: number;
  page_size?: number;
}) {
  const { data } = await client.get('/iqc/aql-profiles', { params });
  return data;
}

export async function createAqlProfile(payload: {
  supplier_id: string;
  material_id: string;
  base_aql: number;
  current_aql: number;
  product_line_code: string;
  min_aql?: number;
  max_aql?: number;
  inspection_level?: string;
}) {
  const { data } = await client.post('/iqc/aql-profiles', payload);
  return data as AqlProfile;
}

export async function getAqlProfile(profileId: string) {
  const { data } = await client.get(`/api/iqc/aql-profiles/${profileId}`);
  return data as AqlProfile;
}

export async function updateAqlProfile(profileId: string, payload: {
  min_aql?: number;
  max_aql?: number;
  inspection_level?: string;
}) {
  const { data } = await client.put(`/api/iqc/aql-profiles/${profileId}`, payload);
  return data as AqlProfile;
}

export async function getAqlProfileHistory(profileId: string) {
  const { data } = await client.get(`/api/iqc/aql-profiles/${profileId}/history`);
  return data;
}

// ── Recommendation ──

export async function listAqlRecommendations(params?: {
  status?: string;
  direction?: string;
  supplier_id?: string;
  material_id?: string;
  page?: number;
  page_size?: number;
}) {
  const { data } = await client.get('/iqc/aql-recommendations', { params });
  return data;
}

export async function getAqlRecommendation(recommendationId: string) {
  const { data } = await client.get(`/api/iqc/aql-recommendations/${recommendationId}`);
  return data as AqlRecommendation;
}

export async function engineerApproveRecommendation(recommendationId: string, reason?: string) {
  const { data } = await client.post(`/api/iqc/aql-recommendations/${recommendationId}/engineer-approve`, { reason });
  return data as AqlRecommendation;
}

export async function engineerRejectRecommendation(recommendationId: string, reason: string) {
  const { data } = await client.post(`/api/iqc/aql-recommendations/${recommendationId}/engineer-reject`, { reason });
  return data as AqlRecommendation;
}

export async function forwardRecommendation(recommendationId: string) {
  const { data } = await client.post(`/api/iqc/aql-recommendations/${recommendationId}/forward`);
  return data as AqlRecommendation;
}

export async function managerApproveRecommendation(recommendationId: string, reason?: string) {
  const { data } = await client.post(`/api/iqc/aql-recommendations/${recommendationId}/manager-approve`, { reason });
  return data as AqlRecommendation;
}

export async function managerRejectRecommendation(recommendationId: string, reason: string) {
  const { data } = await client.post(`/api/iqc/aql-recommendations/${recommendationId}/manager-reject`, { reason });
  return data as AqlRecommendation;
}

export async function markRecommendationExpired(recommendationId: string) {
  const { data } = await client.post(`/api/iqc/aql-recommendations/${recommendationId}/expired`);
  return data as AqlRecommendation;
}

export async function triggerAqlEvaluation(payload: { supplier_id: string; material_id: string }) {
  const { data } = await client.post('/iqc/aql-recommendations/trigger', payload);
  return data;
}

export async function previewAqlRecommendation(payload: { supplier_id: string; material_id: string }) {
  const { data } = await client.post('/iqc/aql-recommendations/preview', payload);
  return data as AqlPreviewResult;
}

// ── Quality Snapshot ──

export async function getAqlQualitySnapshot(supplierId: string, materialId: string) {
  const { data } = await client.get(`/api/iqc/aql-quality-snapshot/${supplierId}/${materialId}`);
  return data as AqlQualitySnapshot;
}

export async function getAqlQualitySnapshotTrend(supplierId: string, materialId: string) {
  const { data } = await client.get(`/api/iqc/aql-quality-snapshot/${supplierId}/${materialId}/trend`);
  return data;
}

// ── Config ──

export async function listAqlConfigs(productLineCode?: string) {
  const { data } = await client.get('/iqc/aql-config', { params: { product_line_code: productLineCode } });
  return data as AqlConfig[];
}

export async function updateAqlConfig(configKey: string, payload: { config_value: string }) {
  const { data } = await client.put(`/api/iqc/aql-config/${configKey}`, payload);
  return data as AqlConfig;
}

export async function resetAqlConfigs() {
  const { data } = await client.post('/iqc/aql-config/reset');
  return data;
}
