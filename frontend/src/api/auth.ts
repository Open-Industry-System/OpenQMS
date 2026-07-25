import client from "./client";
import type { LoginRequest, TokenResponse, User, RegisterRequest, UserUpdateRequest, AssignableRoleOption, Factory } from "../types";

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

export async function registerUser(data: RegisterRequest): Promise<User> {
  const resp = await client.post("/auth/register", data);
  return resp.data;
}

export async function updateUser(user_id: string, payload: UserUpdateRequest): Promise<User> {
  const resp = await client.patch(`/auth/users/${user_id}`, payload);
  return resp.data;
}

export async function deleteUser(user_id: string): Promise<void> {
  await client.delete(`/auth/users/${user_id}`);
}

export async function listAssignableRoles(): Promise<AssignableRoleOption[]> {
  const resp = await client.get("/auth/roles");
  return resp.data;
}

export async function listFactories(): Promise<Factory[]> {
  const resp = await client.get("/auth/factories");
  return resp.data;
}
