export interface PublicDemoEnv {
  readonly VITE_PUBLIC_DEMO_ENABLED?: string;
  readonly VITE_PUBLIC_DEMO_USERNAME?: string;
  readonly VITE_PUBLIC_DEMO_PASSWORD?: string;
  readonly VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS?: string;
}

export interface PublicDemoAccount {
  username: string;
  password: string;
}

export interface PublicDemoConfig {
  username: string;
  password: string;
  additionalAccounts?: PublicDemoAccount[];
}

const ADDITIONAL_DEMO_USERNAMES = ["engineer", "manager"] as const;

function parseAdditionalAccounts(value: string): PublicDemoAccount[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return null;
  }

  if (!Array.isArray(parsed) || parsed.length !== ADDITIONAL_DEMO_USERNAMES.length) return null;

  const accounts = new Map<string, PublicDemoAccount>();
  for (const account of parsed) {
    if (
      !account
      || typeof account !== "object"
      || Array.isArray(account)
      || Object.keys(account).length !== 2
      || !("username" in account)
      || !("password" in account)
    ) return null;

    const { username: rawUsername, password } = account as { username: unknown; password: unknown };
    if (typeof rawUsername !== "string" || typeof password !== "string") return null;

    const username = rawUsername.trim();
    if (
      !ADDITIONAL_DEMO_USERNAMES.includes(username as typeof ADDITIONAL_DEMO_USERNAMES[number])
      || !password.trim()
      || accounts.has(username)
    ) return null;

    accounts.set(username, { username, password });
  }

  return ADDITIONAL_DEMO_USERNAMES.map((username) => accounts.get(username)!);
}

export function getPublicDemoConfig(
  env: PublicDemoEnv = import.meta.env,
): PublicDemoConfig | null {
  if (env.VITE_PUBLIC_DEMO_ENABLED !== "true") return null;

  const username = env.VITE_PUBLIC_DEMO_USERNAME?.trim();
  const password = env.VITE_PUBLIC_DEMO_PASSWORD;
  if (!username || !password?.trim()) return null;

  const config = { username, password };
  const additionalAccountsValue = env.VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS;
  if (!additionalAccountsValue?.trim()) return config;

  const additionalAccounts = parseAdditionalAccounts(additionalAccountsValue);
  if (!additionalAccounts) return null;

  return { ...config, additionalAccounts };
}
