import { readFileSync } from "fs";
import path from "path";
import type { Page } from "@playwright/test";

const STORAGE_DIR = "e2e/.storage-state";
const STORAGE_ORIGIN = "http://localhost:5174";

type StorageEntry = { name: string; value: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function storageEntries(username: string): StorageEntry[] {
  const statePath = path.resolve(process.cwd(), storageStatePath(username));
  let state: unknown;
  try {
    state = JSON.parse(readFileSync(statePath, "utf-8"));
  } catch (error) {
    throw new Error(
      `[e2e] unable to read storage state for ${username} at ${statePath}: ${String(error)}`,
    );
  }

  const origins = isRecord(state) && Array.isArray(state.origins) ? state.origins : null;
  if (!origins) {
    throw new Error(`[e2e] malformed storage state for ${username}: missing origins`);
  }
  const origin = origins.find(
    (candidate) => isRecord(candidate) && candidate.origin === STORAGE_ORIGIN,
  );
  if (!isRecord(origin)) {
    throw new Error(
      `[e2e] storage state for ${username} has no ${STORAGE_ORIGIN} origin`,
    );
  }

  const rawEntries = origin.localStorage;
  if (!Array.isArray(rawEntries)) {
    throw new Error(
      `[e2e] malformed storage state for ${username}: ${STORAGE_ORIGIN} localStorage is missing`,
    );
  }
  if (
    rawEntries.some(
      (entry) =>
        !isRecord(entry) || typeof entry.name !== "string" || typeof entry.value !== "string",
    )
  ) {
    throw new Error(
      `[e2e] malformed storage state for ${username}: invalid localStorage entry`,
    );
  }

  const entries = rawEntries as StorageEntry[];
  const accessToken = entries.find((entry) => entry.name === "access_token")?.value;
  if (!accessToken || accessToken.split(".").length !== 3) {
    throw new Error(
      `[e2e] storage state for ${username} has no valid access_token`,
    );
  }
  return entries;
}

export async function loginAs(page: Page, username: string): Promise<void> {
  const entries = storageEntries(username);
  await page.addInitScript(
    ({ origin, entries: savedEntries }: { origin: string; entries: StorageEntry[] }) => {
      if (window.location.origin !== origin) return;
      for (const { name, value } of savedEntries) window.localStorage.setItem(name, value);
    },
    { origin: STORAGE_ORIGIN, entries },
  );
  await page.goto("/dashboard");
  await page.waitForURL(/\/dashboard(?:\/|$)/);
}

export function storageStatePath(username: string): string {
  return `${STORAGE_DIR}/${username}.json`;
}
