# Oracle CI/CD Implementation Plan

**Goal:** Integrate the deployed production baseline into current main, verify it, then automate per-PR previews and guarded main releases.

**Architecture:** An isolated integration branch combines production release guards with current tenant and application behavior. GitHub CI gates immutable SHA deployments; previews use separate databases, configuration, networks and bounded resources on the Oracle host.

## Task 1: Integrate the production baseline

- [x] Create isolated worktree from origin/main (2dbb84b1).
- [x] Merge deployed commit d8648c15 without committing.
- [ ] Resolve conflicts: keep current tenant coordinator and main migration tests; preserve production session isolation and release safety.
- [ ] Verify a single migration head covering both histories; add merge revision if required.
- [ ] Run focused release, configuration, authentication and migration checks, frontend tests/typecheck/build, then current main acceptance checks against a dedicated test database.
- [ ] Review integration diff before committing or publishing.

## Task 2: Automate deployments

- [x] Design transport and trusted PR eligibility around verified production runbook (details below).
- [ ] Add fail-closed tests for SHA/state validation, failed CI, fork PRs, closed PR cleanup and production/preview separation.
- [ ] Add workflows and host deployment scripts preserving immutable source/image/target identity and release sequence.
- [ ] Add bounded per-PR Compose resources, independent data, secrets, routing and cleanup.
- [ ] Configure GitHub environments/secrets and server access without exposing secrets to PR code.
- [ ] Verify DNS/TLS and lifecycle on a preview before allowing production rollout.

## Task 3: Verify and deliver

- [ ] Review spec compliance and code quality; resolve findings.
- [ ] Record command evidence, remaining external configuration, and runtime limits in PROGRESS.md and deployment documentation.
- [ ] Publish reviewable integration PR; enable production only after required checks and safe initial rollout.

## Confirmed deployment design

Keep production Caddy proxy trust at 172.30.0.10. Reload validated, host-generated per-PR routes through a container-local Unix socket; expose no admin TCP port. An external edge network connects production web only to preview web; previews never join the production internal network. Each preview owns PostgreSQL/Redis/Neo4j, secrets and data; enforce at most two live previews, container CPU/memory/PID limits and rotated logs. Use wildcard DNS with individual HTTP-01 certificates; no wildcard certificate credentials required.

Privileged workflows run deployment code from the protected default branch. Resolve exact tested merge SHA (CI github.sha is not necessarily workflow_run.head_sha), verify its safe receipt and current PR state, reject forks/untrusted authors/stale runs. Recheck before publishing. A PR source tree must never supply privileged deployment scripts. Main deploys serialize without cancellation during migration. Close cleanup removes route first, then only identically labeled PR resources. Host flock serializes builds and changes.

Extract immutable git archive/manifest/hash/mode/image-revision/image-ID handling from the production runbook into an orchestrator; preserve make deploy-release checks and target/test/runtime identity. Update old runbook test setup to the main owned PostgreSQL resource contract. Host transport may use existing public SSH22 with a dedicated restricted key and pinned host identity; Tailscale OAuth requires new credentials and is not presently configured.

Verification so far: release order and target identity pure tests 41 passed; production configuration/wrapper, initialization, backup, manifest, proxy probe and distinct-database pure tests 196 passed. No production rollout has been executed.
