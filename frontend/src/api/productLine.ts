import client from "./client";
import type { ProductLine } from "../types";

export async function listProductLines(isActive?: boolean): Promise<ProductLine[]> {
  const params: Record<string, unknown> = {};
  if (isActive !== undefined) params.is_active = isActive;
  const resp = await client.get("/product-lines", { params });
  return resp.data.items;
}

export async function createProductLine(data: { code: string; name: string }): Promise<ProductLine> {
  const resp = await client.post("/product-lines", data);
  return resp.data;
}

export async function updateProductLine(code: string, data: { name?: string; is_active?: boolean }): Promise<ProductLine> {
  const resp = await client.put(`/product-lines/${code}`, data);
  return resp.data;
}

export async function deleteProductLine(code: string): Promise<void> {
  await client.delete(`/product-lines/${code}`);
}
