import client from "./client";
import type {
  InspectionCharacteristic,
  InspectionCharacteristicListResponse,
  CreateICRequest,
  SampleBatch,
  ChartDataResponse,
  CapabilityResponse,
  SPCAlarm,
  SPCAlarmListResponse,
  ControlLimitSnapshot,
} from "../types/spc";

export async function listInspectionCharacteristics(params: {
  page?: number;
  page_size?: number;
  product_line?: string;
  process_name?: string;
}): Promise<InspectionCharacteristicListResponse> {
  const resp = await client.get("/spc/inspection-characteristics", { params });
  return resp.data;
}

export async function getInspectionCharacteristic(id: string): Promise<InspectionCharacteristic> {
  const resp = await client.get(`/spc/inspection-characteristics/${id}`);
  return resp.data;
}

export async function createInspectionCharacteristic(data: CreateICRequest): Promise<InspectionCharacteristic> {
  const resp = await client.post("/spc/inspection-characteristics", data);
  return resp.data;
}

export async function updateInspectionCharacteristic(
  id: string,
  data: Partial<CreateICRequest>
): Promise<InspectionCharacteristic> {
  const resp = await client.put(`/spc/inspection-characteristics/${id}`, data);
  return resp.data;
}

export async function deleteInspectionCharacteristic(id: string): Promise<{ message: string }> {
  const resp = await client.delete(`/spc/inspection-characteristics/${id}`);
  return resp.data;
}

export async function lockControlLimits(id: string, locked: boolean): Promise<InspectionCharacteristic> {
  const resp = await client.post(`/spc/inspection-characteristics/${id}/lock-limits`, { locked });
  return resp.data;
}

export async function addSampleBatch(
  id: string,
  data: {
    batch_no: string;
    sampled_at: string;
    values?: number[];
    inspected_count?: number;
    defect_count?: number;
  }
): Promise<SampleBatch> {
  const resp = await client.post(`/spc/inspection-characteristics/${id}/samples`, data);
  return resp.data;
}

export async function getSnapshots(icId: string): Promise<ControlLimitSnapshot[]> {
  const resp = await client.get(`/spc/inspection-characteristics/${icId}/snapshots`);
  return resp.data;
}

export async function activateSnapshot(icId: string, snapshotId: string): Promise<ControlLimitSnapshot> {
  const resp = await client.patch(`/spc/inspection-characteristics/${icId}/snapshots/${snapshotId}/activate`);
  return resp.data;
}

export async function getChartData(id: string): Promise<ChartDataResponse> {
  const resp = await client.get(`/spc/inspection-characteristics/${id}/chart-data`);
  return resp.data;
}

export async function getCapability(id: string): Promise<CapabilityResponse> {
  const resp = await client.get(`/spc/inspection-characteristics/${id}/capability`);
  return resp.data;
}

export async function listAlarms(
  id: string,
  params: { page?: number; page_size?: number }
): Promise<SPCAlarmListResponse> {
  const resp = await client.get(`/spc/inspection-characteristics/${id}/alarms`, { params });
  return resp.data;
}

export async function acknowledgeAlarm(alarmId: string): Promise<SPCAlarm> {
  const resp = await client.post(`/spc/alarms/${alarmId}/acknowledge`);
  return resp.data;
}

export async function createCAPAFromAlarm(alarmId: string): Promise<{ capa_id: string; document_number: string }> {
  const resp = await client.post(`/spc/alarms/${alarmId}/create-capa`);
  return resp.data;
}
