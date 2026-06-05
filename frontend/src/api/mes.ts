import client from "./client";
import type {
  MESConnection, MESConnectionCreate, MESProductionOrder,
  MESEquipmentStatus, MESScrapRecord, MESDashboardData,
} from "../types/mes";

export const listConnections = (page = 1, page_size = 20) =>
  client.get("/mes/connections", { params: { page, page_size } }).then((r) => r.data);

export const createConnection = (data: MESConnectionCreate) =>
  client.post("/mes/connections", data).then((r) => r.data);

export const updateConnection = (id: string, data: Partial<MESConnectionCreate>) =>
  client.put(`/mes/connections/${id}`, data).then((r) => r.data);

export const deleteConnection = (id: string) =>
  client.delete(`/mes/connections/${id}`).then((r) => r.data);

export const testConnection = (id: string) =>
  client.post(`/mes/connections/${id}/test`).then((r) => r.data);

export const manualSync = (id: string) =>
  client.post(`/mes/connections/${id}/sync`).then((r) => r.data);

export const listProductionOrders = (page = 1, page_size = 20, product_line_code?: string) =>
  client.get("/mes/production-orders", { params: { page, page_size, product_line_code } }).then((r) => r.data);

export const getProductionOrder = (id: string) =>
  client.get(`/mes/production-orders/${id}`).then((r) => r.data);

export const listEquipmentStatus = (product_line_code?: string) =>
  client.get("/mes/equipment-status", { params: { product_line_code } }).then((r) => r.data);

export const listScrapRecords = (page = 1, page_size = 20, product_line_code?: string) =>
  client.get("/mes/scrap-records", { params: { page, page_size, product_line_code } }).then((r) => r.data);

export const getMESDashboard = (product_line_code?: string) =>
  client.get("/mes/dashboard", { params: { product_line_code } }).then((r) => r.data);
