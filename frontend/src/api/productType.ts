import client from "./client";
import type { ProductType } from "../types";

export async function listProductTypes(isActive?: boolean): Promise<ProductType[]> {
  const params: Record<string, unknown> = {};
  if (isActive !== undefined) params.is_active = isActive;
  const resp = await client.get("/product-types", { params });
  return resp.data.items;
}

export async function createProductType(data: { code: string; name: string; description?: string | null }): Promise<ProductType> {
  const resp = await client.post("/product-types", data);
  return resp.data;
}

export async function updateProductType(code: string, data: { name?: string; description?: string | null; is_active?: boolean }): Promise<ProductType> {
  const resp = await client.put(`/product-types/${code}`, data);
  return resp.data;
}

export async function deleteProductType(code: string): Promise<void> {
  await client.delete(`/product-types/${code}`);
}
