import client from "./client";
import type {
  APQPListResponse,
  APQPProject,
  APQPProjectCreate,
  APQPProjectUpdate,
  APQPGateTransition,
  APQPProjectStats,
} from "../types";

export async function listAPQPProjects(params: {
  page?: number;
  page_size?: number;
  project_status?: string;
  current_phase?: number;
}): Promise<APQPListResponse> {
  const res = await client.get("/apqp-projects", { params });
  return res.data;
}

export async function getAPQPProject(id: string): Promise<APQPProject> {
  const res = await client.get(`/apqp-projects/${id}`);
  return res.data;
}

export async function createAPQPProject(data: APQPProjectCreate): Promise<APQPProject> {
  const res = await client.post("/apqp-projects", data);
  return res.data;
}

export async function updateAPQPProject(id: string, data: APQPProjectUpdate): Promise<APQPProject> {
  const res = await client.put(`/apqp-projects/${id}`, data);
  return res.data;
}

export async function transitionAPQPProject(id: string, data: APQPGateTransition): Promise<APQPProject> {
  const res = await client.post(`/apqp-projects/${id}/transition`, data);
  return res.data;
}

export async function getAPQPProjectStats(): Promise<APQPProjectStats> {
  const res = await client.get("/apqp-projects/stats");
  return res.data;
}
