export type TokenState = "missing" | "malformed" | "expired" | "valid";

type JwtPayload = Record<string, unknown>;

function decodePayload(token: string): JwtPayload | null {
  try {
    const encoded = token.split(".")[1];
    if (!encoded || encoded.length % 4 === 1) return null;
    const normalized = encoded.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(encoded.length / 4) * 4, "=");
    const payload: unknown = JSON.parse(atob(normalized));
    return typeof payload === "object" && payload !== null && !Array.isArray(payload)
      ? payload as JwtPayload
      : null;
  } catch {
    return null;
  }
}

export function classifyToken(token: string | null): TokenState {
  if (!token) return "missing";

  const payload = decodePayload(token);
  if (!payload) return "malformed";
  const exp = payload.exp;
  if (typeof exp !== "number" || !Number.isFinite(exp)) return "malformed";
  return exp * 1000 < Date.now() ? "expired" : "valid";
}

export function getTokenSubject(token: string | null): string | null {
  if (!token) return null;
  const sub = decodePayload(token)?.sub;
  return typeof sub === "string" && sub.length > 0 ? sub : null;
}
