import client from "./client";
import type { LoginRequest, TokenResponse, User } from "../types";

export async function login(data: LoginRequest): Promise<TokenResponse> {
  const resp = await client.post("/auth/login", data);
  return resp.data;
}

export async function refreshToken(refresh_token: string): Promise<{ access_token: string; refresh_token: string }> {
  const resp = await client.post("/auth/refresh", { refresh_token });
  return resp.data;
}

export async function getMe(): Promise<User> {
  const resp = await client.get("/auth/me");
  return resp.data;
}

export async function listUsers(): Promise<User[]> {
  const resp = await client.get("/auth/users");
  return resp.data;
}
