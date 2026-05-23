import client from "./client";
import type {
  Gauge,
  GaugeListResponse,
  GaugeCalibration,
  GaugeCalibrationListResponse,
  GrrStudy,
  GrrStudyListResponse,
  GrrResult,
  BiasStudy,
  BiasStudyListResponse,
  BiasResult,
  LinearityStudy,
  LinearityStudyListResponse,
  LinearityResult,
  StabilityStudy,
  StabilityStudyListResponse,
  StabilityResult,
  AttributeStudy,
  AttributeStudyListResponse,
  AttributeResult,
  MsaStudyOverviewListResponse,
  MsaSpcCharacteristic,
} from "../types";

// ─── Gauge ───

export async function listGauges(params?: Record<string, unknown>): Promise<GaugeListResponse> {
  const resp = await client.get("/gauges", { params });
  return resp.data;
}

export async function getExpiringGauges(days = 30): Promise<GaugeListResponse> {
  const resp = await client.get("/gauges/expiring", { params: { days } });
  return resp.data;
}

export async function createGauge(
  data: Omit<Gauge, "gauge_id" | "status" | "created_by" | "created_at" | "updated_at">
): Promise<Gauge> {
  const resp = await client.post("/gauges", data);
  return resp.data;
}

export async function getGauge(id: string): Promise<Gauge> {
  const resp = await client.get(`/gauges/${id}`);
  return resp.data;
}

export async function updateGauge(id: string, data: Partial<Gauge>): Promise<Gauge> {
  const resp = await client.put(`/gauges/${id}`, data);
  return resp.data;
}

export async function deleteGauge(id: string): Promise<void> {
  await client.delete(`/gauges/${id}`);
}

export async function listCalibrations(gaugeId: string): Promise<GaugeCalibration[]> {
  const resp = await client.get(`/gauges/${gaugeId}/calibrations`);
  return resp.data.items;
}

export async function createCalibration(
  gaugeId: string,
  data: Omit<GaugeCalibration, "calibration_id" | "gauge_id" | "created_at">
): Promise<GaugeCalibration> {
  const resp = await client.post(`/gauges/${gaugeId}/calibrations`, data);
  return resp.data;
}

// ─── GRR ───

export async function listGrrStudies(params?: Record<string, unknown>): Promise<GrrStudyListResponse> {
  const resp = await client.get("/msa/grr", { params });
  return resp.data;
}

export async function createGrrStudy(
  data: Omit<GrrStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">
): Promise<GrrStudy> {
  const resp = await client.post("/msa/grr", data);
  return resp.data;
}

export async function getGrrStudy(id: string): Promise<GrrStudy> {
  const resp = await client.get(`/msa/grr/${id}`);
  return resp.data;
}

export async function updateGrrStudy(id: string, data: Partial<GrrStudy>): Promise<GrrStudy> {
  const resp = await client.put(`/msa/grr/${id}`, data);
  return resp.data;
}

export async function deleteGrrStudy(id: string): Promise<void> {
  await client.delete(`/msa/grr/${id}`);
}

export async function upsertGrrMeasurements(id: string, measurements: { appraiser_name: string; part_no: string; trial_no: number; value: number }[]): Promise<{ message: string; count: number }> {
  const resp = await client.post(`/msa/grr/${id}/measurements`, { measurements });
  return resp.data;
}

export async function getGrrMeasurements(id: string): Promise<{ measurement_id: string; study_id: string; appraiser_name: string; part_no: string; trial_no: number; value: number }[]> {
  const resp = await client.get(`/msa/grr/${id}/measurements`);
  return resp.data;
}

export async function computeGrr(id: string): Promise<GrrResult> {
  const resp = await client.post(`/msa/grr/${id}/compute`);
  return resp.data;
}

export async function getGrrResult(id: string): Promise<GrrResult> {
  const resp = await client.get(`/msa/grr/${id}/result`);
  return resp.data;
}

export async function completeGrrStudy(id: string, accepted = true): Promise<GrrStudy> {
  const resp = await client.post(`/msa/grr/${id}/complete`, null, { params: { accepted } });
  return resp.data;
}

// ─── Bias ───

export async function listBiasStudies(params?: Record<string, unknown>): Promise<BiasStudyListResponse> {
  const resp = await client.get("/msa/bias", { params });
  return resp.data;
}

export async function createBiasStudy(
  data: Omit<BiasStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">
): Promise<BiasStudy> {
  const resp = await client.post("/msa/bias", data);
  return resp.data;
}

export async function getBiasStudy(id: string): Promise<BiasStudy> {
  const resp = await client.get(`/msa/bias/${id}`);
  return resp.data;
}

export async function updateBiasStudy(id: string, data: Partial<BiasStudy>): Promise<BiasStudy> {
  const resp = await client.put(`/msa/bias/${id}`, data);
  return resp.data;
}

export async function deleteBiasStudy(id: string): Promise<void> {
  await client.delete(`/msa/bias/${id}`);
}

export async function upsertBiasMeasurements(id: string, measurements: { value: number; sequence_no: number }[]): Promise<{ message: string; count: number }> {
  const resp = await client.post(`/msa/bias/${id}/measurements`, { measurements });
  return resp.data;
}

export async function getBiasMeasurements(id: string): Promise<{ measurement_id: string; study_id: string; value: number; sequence_no: number }[]> {
  const resp = await client.get(`/msa/bias/${id}/measurements`);
  return resp.data;
}

export async function computeBias(id: string): Promise<BiasResult> {
  const resp = await client.post(`/msa/bias/${id}/compute`);
  return resp.data;
}

export async function getBiasResult(id: string): Promise<BiasResult> {
  const resp = await client.get(`/msa/bias/${id}/result`);
  return resp.data;
}

export async function completeBiasStudy(id: string, accepted = true): Promise<BiasStudy> {
  const resp = await client.post(`/msa/bias/${id}/complete`, null, { params: { accepted } });
  return resp.data;
}

// ─── Linearity ───

export async function listLinearityStudies(params?: Record<string, unknown>): Promise<LinearityStudyListResponse> {
  const resp = await client.get("/msa/linearity", { params });
  return resp.data;
}

export async function createLinearityStudy(
  data: Omit<LinearityStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">
): Promise<LinearityStudy> {
  const resp = await client.post("/msa/linearity", data);
  return resp.data;
}

export async function getLinearityStudy(id: string): Promise<LinearityStudy> {
  const resp = await client.get(`/msa/linearity/${id}`);
  return resp.data;
}

export async function updateLinearityStudy(id: string, data: Partial<LinearityStudy>): Promise<LinearityStudy> {
  const resp = await client.put(`/msa/linearity/${id}`, data);
  return resp.data;
}

export async function deleteLinearityStudy(id: string): Promise<void> {
  await client.delete(`/msa/linearity/${id}`);
}

export async function upsertLinearityMeasurements(id: string, measurements: { reference_value: number; measured_value: number; sequence_no: number }[]): Promise<{ message: string; count: number }> {
  const resp = await client.post(`/msa/linearity/${id}/measurements`, { measurements });
  return resp.data;
}

export async function getLinearityMeasurements(id: string): Promise<{ measurement_id: string; study_id: string; reference_value: number; measured_value: number; sequence_no: number }[]> {
  const resp = await client.get(`/msa/linearity/${id}/measurements`);
  return resp.data;
}

export async function computeLinearity(id: string): Promise<LinearityResult> {
  const resp = await client.post(`/msa/linearity/${id}/compute`);
  return resp.data;
}

export async function getLinearityResult(id: string): Promise<LinearityResult> {
  const resp = await client.get(`/msa/linearity/${id}/result`);
  return resp.data;
}

export async function completeLinearityStudy(id: string, accepted = true): Promise<LinearityStudy> {
  const resp = await client.post(`/msa/linearity/${id}/complete`, null, { params: { accepted } });
  return resp.data;
}

// ─── Stability ───

export async function listStabilityStudies(params?: Record<string, unknown>): Promise<StabilityStudyListResponse> {
  const resp = await client.get("/msa/stability", { params });
  return resp.data;
}

export async function createStabilityStudy(
  data: Omit<StabilityStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">
): Promise<StabilityStudy> {
  const resp = await client.post("/msa/stability", data);
  return resp.data;
}

export async function getStabilityStudy(id: string): Promise<StabilityStudy> {
  const resp = await client.get(`/msa/stability/${id}`);
  return resp.data;
}

export async function updateStabilityStudy(id: string, data: Partial<StabilityStudy>): Promise<StabilityStudy> {
  const resp = await client.put(`/msa/stability/${id}`, data);
  return resp.data;
}

export async function deleteStabilityStudy(id: string): Promise<void> {
  await client.delete(`/msa/stability/${id}`);
}

export async function upsertStabilityMeasurements(id: string, measurements: { measurement_date: string; sample_mean: number; sample_range: number; sequence_no: number }[]): Promise<{ message: string; count: number }> {
  const resp = await client.post(`/msa/stability/${id}/measurements`, { measurements });
  return resp.data;
}

export async function getStabilityMeasurements(id: string): Promise<{ measurement_id: string; study_id: string; measurement_date: string; sample_mean: number; sample_range: number; sequence_no: number }[]> {
  const resp = await client.get(`/msa/stability/${id}/measurements`);
  return resp.data;
}

export async function computeStability(id: string): Promise<StabilityResult> {
  const resp = await client.post(`/msa/stability/${id}/compute`);
  return resp.data;
}

export async function getStabilityResult(id: string): Promise<StabilityResult> {
  const resp = await client.get(`/msa/stability/${id}/result`);
  return resp.data;
}

export async function completeStabilityStudy(id: string, accepted = true): Promise<StabilityStudy> {
  const resp = await client.post(`/msa/stability/${id}/complete`, null, { params: { accepted } });
  return resp.data;
}

// ─── Attribute ───

export async function listAttributeStudies(params?: Record<string, unknown>): Promise<AttributeStudyListResponse> {
  const resp = await client.get("/msa/attribute", { params });
  return resp.data;
}

export async function createAttributeStudy(
  data: Omit<AttributeStudy, "study_id" | "study_no" | "status" | "accepted_by" | "created_by" | "created_at" | "updated_at">
): Promise<AttributeStudy> {
  const resp = await client.post("/msa/attribute", data);
  return resp.data;
}

export async function getAttributeStudy(id: string): Promise<AttributeStudy> {
  const resp = await client.get(`/msa/attribute/${id}`);
  return resp.data;
}

export async function updateAttributeStudy(id: string, data: Partial<AttributeStudy>): Promise<AttributeStudy> {
  const resp = await client.put(`/msa/attribute/${id}`, data);
  return resp.data;
}

export async function deleteAttributeStudy(id: string): Promise<void> {
  await client.delete(`/msa/attribute/${id}`);
}

export async function upsertAttributeMeasurements(id: string, measurements: { appraiser_name: string; part_no: string; known_standard: string; appraiser_decision: string; trial_no?: number }[]): Promise<{ message: string; count: number }> {
  const resp = await client.post(`/msa/attribute/${id}/measurements`, { measurements });
  return resp.data;
}

export async function getAttributeMeasurements(id: string): Promise<{ measurement_id: string; study_id: string; appraiser_name: string; part_no: string; known_standard: string; appraiser_decision: string; trial_no: number }[]> {
  const resp = await client.get(`/msa/attribute/${id}/measurements`);
  return resp.data;
}

export async function computeAttribute(id: string): Promise<AttributeResult> {
  const resp = await client.post(`/msa/attribute/${id}/compute`);
  return resp.data;
}

export async function getAttributeResult(id: string): Promise<AttributeResult> {
  const resp = await client.get(`/msa/attribute/${id}/result`);
  return resp.data;
}

export async function completeAttributeStudy(id: string, accepted = true): Promise<AttributeStudy> {
  const resp = await client.post(`/msa/attribute/${id}/complete`, null, { params: { accepted } });
  return resp.data;
}

// ─── Overview ───

export async function listMsaStudies(params?: Record<string, unknown>): Promise<MsaStudyOverviewListResponse> {
  const resp = await client.get("/msa/studies", { params });
  return resp.data;
}

export async function listSpcCharacteristics(): Promise<MsaSpcCharacteristic[]> {
  const resp = await client.get("/msa/spc-characteristics");
  return resp.data;
}
