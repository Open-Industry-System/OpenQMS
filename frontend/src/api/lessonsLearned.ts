import client from "./client";
import type { LessonsLearnedResponse, LessonsLearnedRequest } from "../types";

export async function getFMEALessons(
  fmeaId: string,
  body?: LessonsLearnedRequest,
  options?: { signal?: AbortSignal }
): Promise<LessonsLearnedResponse> {
  const resp = await client.post(`/fmea/${fmeaId}/lessons-learned`, body || {}, {
    signal: options?.signal,
  });
  return resp.data;
}

export async function getCAPALessons(
  reportId: string,
  body?: LessonsLearnedRequest,
  options?: { signal?: AbortSignal }
): Promise<LessonsLearnedResponse> {
  const resp = await client.post(`/capa/${reportId}/lessons-learned`, body || {}, {
    signal: options?.signal,
  });
  return resp.data;
}
