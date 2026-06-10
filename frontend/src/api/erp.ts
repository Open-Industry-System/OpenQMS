import client from "./client";
import type {
  ERPConnection,
  PaginatedResponse,
  ERPSupplier,
  ERPCustomer,
  ERPMaterial,
  ERPLocation,
  ERPPurchaseOrder,
  ERPSalesOrder,
  ERPInventoryBalance,
  ERPShipment,
  ERPCostRecord,
  TraceabilityResponse,
  ERPDashboardData,
} from "../types/erp";

// ─── Connections ───

export async function fetchERPConnections(
  page = 1,
  page_size = 20,
): Promise<PaginatedResponse<ERPConnection>> {
  const resp = await client.get<PaginatedResponse<ERPConnection>>(
    "/erp/connections",
    { params: { page, page_size } },
  );
  return resp.data;
}

export async function fetchERPConnection(id: string): Promise<ERPConnection> {
  const resp = await client.get<ERPConnection>(`/erp/connections/${id}`);
  return resp.data;
}

export async function createERPConnection(
  data: unknown,
): Promise<ERPConnection> {
  const resp = await client.post<ERPConnection>("/erp/connections", data);
  return resp.data;
}

export async function updateERPConnection(
  id: string,
  data: unknown,
): Promise<ERPConnection> {
  const resp = await client.put<ERPConnection>(`/erp/connections/${id}`, data);
  return resp.data;
}

export async function deleteERPConnection(id: string): Promise<void> {
  await client.delete(`/erp/connections/${id}`);
}

export async function testERPConnection(
  id: string,
): Promise<{ success: boolean; message: string }> {
  const resp = await client.post<{ success: boolean; message: string }>(
    `/erp/connections/${id}/test`,
  );
  return resp.data;
}

export async function triggerERPSync(id: string): Promise<void> {
  await client.post(`/erp/connections/${id}/sync`);
}

// ─── Suppliers ───

export async function fetchERPSuppliers(params?: {
  page?: number;
  page_size?: number;
  link_status?: string;
}): Promise<PaginatedResponse<ERPSupplier>> {
  const resp = await client.get<PaginatedResponse<ERPSupplier>>(
    "/erp/suppliers",
    { params },
  );
  return resp.data;
}

export async function linkERPSupplier(
  id: string,
  supplier_id: string,
): Promise<void> {
  await client.post(`/erp/suppliers/${id}/link`, { supplier_id });
}

export async function unlinkERPSupplier(id: string): Promise<void> {
  await client.post(`/erp/suppliers/${id}/unlink`);
}

// ─── Customers ───

export async function fetchERPCustomers(params?: {
  page?: number;
  page_size?: number;
  link_status?: string;
}): Promise<PaginatedResponse<ERPCustomer>> {
  const resp = await client.get<PaginatedResponse<ERPCustomer>>(
    "/erp/customers",
    { params },
  );
  return resp.data;
}

export async function linkERPCustomer(
  id: string,
  customer_id: string,
): Promise<void> {
  await client.post(`/erp/customers/${id}/link`, { customer_id });
}

export async function unlinkERPCustomer(id: string): Promise<void> {
  await client.post(`/erp/customers/${id}/unlink`);
}

// ─── Materials ───

export async function fetchERPMaterials(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<ERPMaterial>> {
  const resp = await client.get<PaginatedResponse<ERPMaterial>>(
    "/erp/materials",
    { params },
  );
  return resp.data;
}

// ─── Locations ───

export async function fetchERPLocations(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<ERPLocation>> {
  const resp = await client.get<PaginatedResponse<ERPLocation>>(
    "/erp/locations",
    { params },
  );
  return resp.data;
}

// ─── Purchase Orders ───

export async function fetchERPPurchaseOrders(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<ERPPurchaseOrder>> {
  const resp = await client.get<PaginatedResponse<ERPPurchaseOrder>>(
    "/erp/purchase-orders",
    { params },
  );
  return resp.data;
}

// ─── Sales Orders ───

export async function fetchERPSalesOrders(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<ERPSalesOrder>> {
  const resp = await client.get<PaginatedResponse<ERPSalesOrder>>(
    "/erp/sales-orders",
    { params },
  );
  return resp.data;
}

// ─── Inventory Balances ───

export async function fetchERPInventoryBalances(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<ERPInventoryBalance>> {
  const resp = await client.get<PaginatedResponse<ERPInventoryBalance>>(
    "/erp/inventory-balances",
    { params },
  );
  return resp.data;
}

// ─── Shipments ───

export async function fetchERPShipments(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<ERPShipment>> {
  const resp = await client.get<PaginatedResponse<ERPShipment>>(
    "/erp/shipments",
    { params },
  );
  return resp.data;
}

// ─── Cost Records ───

export async function fetchERPCostRecords(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<ERPCostRecord>> {
  const resp = await client.get<PaginatedResponse<ERPCostRecord>>(
    "/erp/cost-records",
    { params },
  );
  return resp.data;
}

// ─── Traceability ───

export async function queryERPTraceability(
  lot_no: string,
  direction: "forward" | "backward" = "forward",
): Promise<TraceabilityResponse> {
  const resp = await client.get<TraceabilityResponse>("/erp/traceability", {
    params: { lot_no, direction },
  });
  return resp.data;
}

// ─── Dashboard ───

export async function fetchERPDashboard(): Promise<ERPDashboardData> {
  const resp = await client.get<ERPDashboardData>("/erp/dashboard");
  return resp.data;
}