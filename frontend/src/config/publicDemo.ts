export interface PublicDemoEnv {
  readonly VITE_PUBLIC_DEMO_ENABLED?: string;
  readonly VITE_PUBLIC_DEMO_USERNAME?: string;
  readonly VITE_PUBLIC_DEMO_PASSWORD?: string;
}

export interface PublicDemoConfig {
  username: string;
  password: string;
}

export function getPublicDemoConfig(
  env: PublicDemoEnv = import.meta.env,
): PublicDemoConfig | null {
  if (env.VITE_PUBLIC_DEMO_ENABLED !== "true") return null;

  const username = env.VITE_PUBLIC_DEMO_USERNAME?.trim();
  const password = env.VITE_PUBLIC_DEMO_PASSWORD;
  if (!username || !password?.trim()) return null;

  return { username, password };
}
