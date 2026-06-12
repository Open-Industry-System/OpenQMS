import client from "./client";
import type {
  HeatmapResponse,
  TimelineResponse,
  SupplierDetailResponse,
  ComparisonResponse,
  SnapshotGenerateResponse,
} from "../types";

export const riskMapApi = {
  heatmap: (params: { product_line_code?: string; period?: string }) =>
    client.get<HeatmapResponse>("/supply-chain-risk-map/heatmap", { params }),

  timeline: (params?: { product_line_code?: string }) =>
    client.get<TimelineResponse>("/supply-chain-risk-map/timeline", { params }),

  supplierDetail: (id: string, params?: { product_line_code?: string; period?: string }) =>
    client.get<SupplierDetailResponse>(`/supply-chain-risk-map/suppliers/${id}`, { params }),

  compare: (supplierIds: string[], params?: { product_line_code?: string; period?: string }) =>
    client.post<ComparisonResponse>("/supply-chain-risk-map/suppliers/compare", { supplier_ids: supplierIds }, { params }),

  generateSnapshot: (params?: { product_line_code?: string }) =>
    client.post<SnapshotGenerateResponse>("/supply-chain-risk-map/snapshots/generate", null, { params }),

  exportCsv: (params: { product_line_code?: string; period?: string }) =>
    client.get("/supply-chain-risk-map/export", { params: { ...params, format: "csv" }, responseType: "blob" }),

  exportExcel: (params: { product_line_code?: string; period?: string }) =>
    client.get("/supply-chain-risk-map/export", { params: { ...params, format: "excel" }, responseType: "blob" }),
};