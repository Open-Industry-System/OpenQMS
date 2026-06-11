import client from "./client";

export const riskAlertApi = {
  list: (params: Record<string, unknown>) => client.get("/supplier-risk/alerts", { params }),
  get: (id: string) => client.get(`/supplier-risk/alerts/${id}`),
  handle: (id: string, data: { action: string; note?: string }) => client.post(`/supplier-risk/alerts/${id}/handle`, data),
  createScar: (id: string) => client.post(`/supplier-risk/alerts/${id}/scar`),
  createCapa: (id: string) => client.post(`/supplier-risk/alerts/${id}/capa`),
  evaluateSupplier: (supplierId: string) => client.post(`/supplier-risk/evaluate/${supplierId}`),
  evaluateAll: () => client.post("/supplier-risk/evaluate"),
  dashboard: (params?: Record<string, unknown>) => client.get("/supplier-risk/dashboard", { params }),
  listConfigs: () => client.get("/supplier-risk/configs"),
  updateConfig: (id: string, data: Record<string, unknown>) => client.put(`/supplier-risk/configs/${id}`, data),
  listChannels: () => client.get("/supplier-risk/channels"),
  createChannel: (data: Record<string, unknown>) => client.post("/supplier-risk/channels", data),
  updateChannel: (id: string, data: Record<string, unknown>) => client.put(`/supplier-risk/channels/${id}`, data),
  deleteChannel: (id: string) => client.delete(`/supplier-risk/channels/${id}`),
};
