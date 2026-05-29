import client from "./client";
import type {
  Customer,
  CustomerComplaint,
  CustomerListResponse,
  CustomerQualityDashboard,
  CustomerSummary,
  ComplaintListResponse,
  RMARecord,
  RMARecordListResponse,
} from "../types";

export type CustomerCreatePayload = Pick<Customer, "customer_code" | "name"> &
  Partial<Omit<Customer, "customer_id" | "customer_code" | "name" | "created_by" | "created_at" | "updated_at">>;
export type CustomerUpdatePayload = Partial<CustomerCreatePayload>;

export type ComplaintCreatePayload = Omit<
  CustomerComplaint,
  "complaint_id" | "created_by" | "created_at" | "updated_at" | "closed_at" | "supplier_id"
> & { supplier_id?: string | null };
export type ComplaintUpdatePayload = Partial<ComplaintCreatePayload>;

export type RMARecordCreatePayload = Omit<
  RMARecord,
  "rma_id" | "created_by" | "created_at" | "updated_at" | "closed_at"
>;
export type RMARecordUpdatePayload = Partial<RMARecordCreatePayload> & { closed_at?: string | null };

export async function listCustomers(params: {
  page?: number;
  page_size?: number;
  q?: string;
  segment?: string;
}): Promise<CustomerListResponse> {
  const resp = await client.get("/customers", { params });
  return resp.data;
}

export async function getCustomer(id: string): Promise<Customer> {
  const resp = await client.get(`/customers/${id}`);
  return resp.data;
}

export async function createCustomer(data: CustomerCreatePayload): Promise<Customer> {
  const resp = await client.post("/customers", data);
  return resp.data;
}

export async function updateCustomer(id: string, data: CustomerUpdatePayload): Promise<Customer> {
  const resp = await client.put(`/customers/${id}`, data);
  return resp.data;
}

export async function getCustomerSummary(
  id: string,
  params?: { product_line?: string; date_from?: string; date_to?: string; shipment_qty?: number }
): Promise<CustomerSummary> {
  const resp = await client.get(`/customers/${id}/summary`, { params });
  return resp.data;
}

export async function listComplaints(params: {
  page?: number;
  page_size?: number;
  product_line?: string;
  customer_id?: string;
  status?: string;
  severity?: string;
  overdue?: boolean;
  assignee_id?: string;
}): Promise<ComplaintListResponse> {
  const resp = await client.get("/customer-complaints", { params });
  return resp.data;
}

export async function getComplaint(id: string): Promise<CustomerComplaint> {
  const resp = await client.get(`/customer-complaints/${id}`);
  return resp.data;
}

export async function createComplaint(data: ComplaintCreatePayload): Promise<CustomerComplaint> {
  const resp = await client.post("/customer-complaints", data);
  return resp.data;
}

export async function updateComplaint(
  id: string,
  data: ComplaintUpdatePayload
): Promise<CustomerComplaint> {
  const resp = await client.put(`/customer-complaints/${id}`, data);
  return resp.data;
}

export async function startComplaintInvestigation(id: string): Promise<CustomerComplaint> {
  const resp = await client.post(`/customer-complaints/${id}/start-investigation`);
  return resp.data;
}

export async function markComplaintResponded(id: string): Promise<CustomerComplaint> {
  const resp = await client.post(`/customer-complaints/${id}/mark-responded`);
  return resp.data;
}

export async function cancelComplaint(id: string): Promise<CustomerComplaint> {
  const resp = await client.post(`/customer-complaints/${id}/cancel`);
  return resp.data;
}

export async function closeComplaint(id: string): Promise<CustomerComplaint> {
  const resp = await client.post(`/customer-complaints/${id}/close`);
  return resp.data;
}

export async function linkComplaintCAPA(id: string, capa_ref_id: string): Promise<CustomerComplaint> {
  const resp = await client.post(`/customer-complaints/${id}/link-capa`, null, {
    params: { capa_ref_id },
  });
  return resp.data;
}

export async function createCAPAFromComplaint(
  id: string,
  document_no: string
): Promise<CustomerComplaint> {
  const resp = await client.post(`/customer-complaints/${id}/create-capa`, null, {
    params: { document_no },
  });
  return resp.data;
}

export async function linkComplaintFMEA(id: string, fmea_ref_id: string): Promise<CustomerComplaint> {
  const resp = await client.post(`/customer-complaints/${id}/link-fmea`, null, {
    params: { fmea_ref_id },
  });
  return resp.data;
}

export async function listRMARecords(params: {
  page?: number;
  page_size?: number;
  product_line?: string;
  customer_id?: string;
  complaint_id?: string;
  status?: string;
  responsibility?: string;
  assignee_id?: string;
}): Promise<RMARecordListResponse> {
  const resp = await client.get("/rma-records", { params });
  return resp.data;
}

export async function getRMARecord(id: string): Promise<RMARecord> {
  const resp = await client.get(`/rma-records/${id}`);
  return resp.data;
}

export async function createRMARecord(data: RMARecordCreatePayload): Promise<RMARecord> {
  const resp = await client.post("/rma-records", data);
  return resp.data;
}

export async function updateRMARecord(id: string, data: RMARecordUpdatePayload): Promise<RMARecord> {
  const resp = await client.put(`/rma-records/${id}`, data);
  return resp.data;
}

export async function startRMAAnalysis(id: string): Promise<RMARecord> {
  const resp = await client.post(`/rma-records/${id}/start-analysis`);
  return resp.data;
}

export async function markRMAActionPending(id: string): Promise<RMARecord> {
  const resp = await client.post(`/rma-records/${id}/mark-action-pending`);
  return resp.data;
}

export async function cancelRMA(id: string): Promise<RMARecord> {
  const resp = await client.post(`/rma-records/${id}/cancel`);
  return resp.data;
}

export async function closeRMA(id: string): Promise<RMARecord> {
  const resp = await client.post(`/rma-records/${id}/close`);
  return resp.data;
}

export async function linkRMAComplaint(id: string, complaint_id: string): Promise<RMARecord> {
  const resp = await client.post(`/rma-records/${id}/link-complaint`, null, {
    params: { complaint_id },
  });
  return resp.data;
}

export async function linkRMACAPA(id: string, capa_ref_id: string): Promise<RMARecord> {
  const resp = await client.post(`/rma-records/${id}/link-capa`, null, {
    params: { capa_ref_id },
  });
  return resp.data;
}

export async function linkRMAFMEA(id: string, fmea_ref_id: string): Promise<RMARecord> {
  const resp = await client.post(`/rma-records/${id}/link-fmea`, null, {
    params: { fmea_ref_id },
  });
  return resp.data;
}

export async function getCustomerQualityDashboard(params?: {
  product_line?: string;
  customer_id?: string;
  date_from?: string;
  date_to?: string;
  shipment_qty?: number;
}): Promise<CustomerQualityDashboard> {
  const resp = await client.get("/customer-quality/dashboard", { params });
  return resp.data;
}

export async function getCustomerTrend(
  customer_id: string,
  params?: { product_line?: string; date_from?: string; date_to?: string; shipment_qty?: number }
): Promise<CustomerQualityDashboard["trend"]> {
  const resp = await client.get(`/customer-quality/customers/${customer_id}/trend`, { params });
  return resp.data;
}
