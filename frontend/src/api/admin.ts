import client from "./client";
import type { RoleOption } from "../types";

export async function listRoles(): Promise<RoleOption[]> {
  const resp = await client.get("/admin/roles");
  return resp.data;
}
