import { drainReport } from "./helpers/cleanup-registry";

export default async function globalTeardown() {
  drainReport(); // diagnostic only; real cleanup is per-spec afterEach
  // eslint-disable-next-line no-console
  console.log("[e2e] global teardown done (DB not torn down; run `make e2e-down`).");
}
