export interface PublicDemoEnv {
  readonly VITE_PUBLIC_DEMO_ENABLED?: string;
  readonly VITE_PUBLIC_DEMO_USERNAME?: string;
  readonly VITE_PUBLIC_DEMO_PASSWORD?: string;
  readonly VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS?: string;
}

const ADDITIONAL_DEMO_USERNAME_PAIRS = [
  ["engineer", "manager"],
  ["demo-engineer", "demo-manager"],
] as const;

type AdditionalDemoUsername = (typeof ADDITIONAL_DEMO_USERNAME_PAIRS)[number][number];

export interface PublicDemoAccount {
  username: AdditionalDemoUsername;
  password: string;
}

export function getAdditionalDemoRole(username: AdditionalDemoUsername) {
  return username === "engineer" || username === "demo-engineer" ? "engineer" : "manager";
}

export interface PublicDemoConfig {
  username: string;
  password: string;
  additionalAccounts?: PublicDemoAccount[];
}

function parseAdditionalAccounts(value: string): PublicDemoAccount[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return null;
  }

  if (!Array.isArray(parsed) || parsed.length !== 2) return null;

  const passwordsByUsername = new Map<string, string>();
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
    if (!password.trim() || passwordsByUsername.has(username)) return null;
    passwordsByUsername.set(username, password);
  }

  for (const [engineer, manager] of ADDITIONAL_DEMO_USERNAME_PAIRS) {
    const engineerPassword = passwordsByUsername.get(engineer);
    const managerPassword = passwordsByUsername.get(manager);
    if (engineerPassword !== undefined && managerPassword !== undefined) {
      return [
        { username: engineer, password: engineerPassword },
        { username: manager, password: managerPassword },
      ];
    }
  }
  return null;
}

export function getPublicDemoConfig(
  env: PublicDemoEnv = import.meta.env,
): PublicDemoConfig | null {
  if (env.VITE_PUBLIC_DEMO_ENABLED !== "true") return null;

  const username = env.VITE_PUBLIC_DEMO_USERNAME?.trim();
  const password = env.VITE_PUBLIC_DEMO_PASSWORD;
  if (!username || !password?.trim() || ["admin", "groupadmin"].includes(username.toLowerCase())) return null;

  const config = { username, password };
  const additionalAccountsValue = env.VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS;
  if (!additionalAccountsValue?.trim()) return config;

  const additionalAccounts = parseAdditionalAccounts(additionalAccountsValue);
  if (!additionalAccounts) return null;

  return { ...config, additionalAccounts };
}
