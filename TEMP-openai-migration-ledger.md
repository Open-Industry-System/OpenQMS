# OpenAI API Migration Decision Ledger — OpenQMS R5

2026-11-15. Implementation, base `6f72c971`, draft PR #33.

## Approved scope and decisions

User selected **gpt-6.1-terra**, supplied a dedicated ignored owner-only credential, and explicitly approved “批准，保留 gpt-6.1-terra 并增加 Responses 适配（推荐）”. Existing independent SPEC/QUALITY, precise commits and deterministic/full verification continue. Updates to the existing draft PR are authorized; merge, deployment and production enablement remain outside scope.

One usable approved increment: immutable R5 Responses deployment supports the existing read/query/supplement/save workflow, followed by a real CLOUD synthetic-8D trial. Dependencies: paired additive migration; SDK adapter; server-owned complete typed replay; existing source, recipient, receipt and command fences; deterministic regressions and independent review. LOCAL endpoint and human quality-engineer evaluation remain external prerequisites.

Keep provider=openai; add explicit api_protocol=chat_completions|responses, default old deployments to Chat. Preserve old Chat HMAC serialization exactly; include protocol in Responses HMAC. Existing immutable-row trigger protects the new column. No model-name heuristics, endpoint fallback or auto-retry.

Preserve platform-owned bounded process-local state. Responses uses store=false, full ordered typed replay including encrypted reasoning/assistant phase, and no previous_response_id. This is **not** an account-level Zero Data Retention or regional-processing guarantee. No additional ZDR/residency requirement was supplied; trial material is entirely synthetic.

Routine settings follow the selected model's normal behavior and the user's standing authorization for routine decisions: medium reasoning and medium verbosity, buffered HTTP and standard processing. Existing 30-second HTTP /120-second round /8-tool /16-KiB proposal limits remain. No new token ceiling; bound opaque replay bytes separately. No general-agent migration or prompt-policy rewrite.

## Assessment of every guidance heading

| Guidance | Applicable/support | Decision and evidence |
|---|---|---|
| Model selection | yes/yes | Exact user-selected Terra ID; official tools require Responses. Dedicated-key model metadata GET200, no generation yet. |
| Instruction file naming | no | Preserve existing files; no compatibility instruction file needed. |
| Chat → Responses | yes/yes | Only R5 workflow and propose_d5 gain the new explicit route. Retain general Chat, Anthropic, local JSON and R4b paths. |
| Streaming | no in approved increment | Complete validated turns precede tools/writes; preserve buffered behavior. |
| WebSocket mode | no | Short HTTP-only bounded pilot; no new reconnect/session contract. |
| Privacy / ZDR | yes/partial | Stateless storage control and no reasoning DB/log persistence; no account entitlement claim. |
| Data residency | unknown/account-specific | Keep user-approved first-party endpoint; no new jurisdiction choice. |
| Processing tiers | yes/yes | Ordinary standard service; no priority/flex/batch/reserved workload requested. |
| Prompt cache keys | no new key | Current-model guidance omits new keys; none existed. |
| Extended cache retention | no | Earlier-model capability; no new retention approval. |
| Explicit cache breakpoints | outside approved compatibility increment | No cache-policy optimization or retained state introduced. |
| Cache diagnostics | outside approved result contract | No new provider-ID/usage persistence feature; existing contract exposes neither. |
| State management | yes/yes | Platform owns complete output items, IDs/order/phases; clear with existing expiry/stop. |
| Instruction persistence | yes/yes | Replay original system input every turn. |
| Encrypted reasoning | yes/yes | Request reasoning.encrypted_content; preserve complete items, not summaries/reconstructed text. |
| Reasoning effort | yes/yes | Explicit medium, matching model default; routine choice under user authorization. |
| Reasoning preservation | yes/yes | Replay all bounded round items; no provider-stored response chain. |
| Reasoning summaries/preambles | partial | No new visible reasoning UI; preserve original typed items privately. |
| Verbosity | yes/yes | Explicit medium; preserve ordinary employee-facing behavior. |
| Maximum output tokens | no new limit | Existing application limits bytes/time/tools; reject incomplete turns. |
| Assistant phases | yes/yes | Preserve commentary/final_answer fields on original replay items. |
| Context compaction | no | Eight-tool bounded round, no long-lived history or compaction request. |
| Structured outputs | yes for tools | strict=false retains optional operation; existing server validators remain authoritative. No JSON-only employee text. |
| Tool choice | yes/yes | Preserve automatic selection among four fixed server-dispatched tools; no hosted tools. |
| Tool search/additional tools | no | Fixed four-tool catalog needs no dynamic discovery. |
| Parallel tool calls | preserve | Keep batch handling, established execution order and deferred employee messages; no concurrent execution added. |
| Programmatic tool calling | no | No code execution or new orchestration approved. |
| Model-aligned interfaces | no redesign | Preserve existing business tools, argument schemas, permissions and receipts. |

## Required workloads and validation

| Workload | Route and coverage | Status |
|---|---|---|
| R5 workflow | Explicit Responses deployment; deterministic HTTP read→save, reasoning/phase replay, supplement/batch order, replacement/retry | New five actual HTTP/sandbox cases passed; full gate pending |
| R5 propose_d5 | Same approved egress; no opaque provider items in HTTP DTO; current source revoke tests | pending |
| Deployment/task binding | Paired additive column/check; legacy HMAC and row preservation, immutable protocol, guarded downgrade and parity | Eight focused cases passed; full migration/provider preflight 527 passed, 2 skipped |
| Retained providers/consumers | Existing adapter, R4b, D5 commands/staff/visibility/review/native regressions | pending |
| Complete verification | Documented full suites plus independent review; preserve failed attempts | pending |
| Real CLOUD trial | Dedicated Terra credential reference, actual sidebar/D4 read/report receipt; human judgment separate | pending |

## Official evidence and SDK

- [Terra model](https://developers.openai.com/api/docs/models/gpt-6.1-terra): tool calls require Responses; exact ID retained.
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling): replay reasoning items and exact call IDs; strict=false preserves existing optional arguments.
- Existing direct OpenAI Python SDK **2.41.1** supports Responses; no dependency upgrade/framework replacement planned. Provider/framework reference reviewed; third-party routers/frameworks are not used by this path.

## Outcome

Independent static SPEC and QUALITY reviews approved the frozen 31-file candidate; no unresolved Critical/Important. Focused verification passed; complete gates are running. Implementation and complete acceptance remain distinct. No live generation, approved Responses deployment or human quality acceptance claimed. LOCAL endpoint and real engineer evaluation pending. Credential plaintext stays outside Git/logs/UI/plugin environment.

## Real sidebar preparation finding

The first normal-app Chromium trial selected the approved deployment and created a task, but root-only creation lacked an explicit source coordinate and stayed blocked_capability. No generation was called. RED regression reproduced the omission. The explicit root-only R5 intent now binds the unique current visible proof through the existing source validator and unchanged authorization intersection; free chat, R4b and explicit scopes remain unchanged. Ten deterministic actual HTTP/sandbox cases passed, independent SPEC/QUALITY approved. The interrupted full make is recorded as incomplete; restart on the next precise commit. Latest main d3c0ada8 retained via 9941d647; both migration heads remain singular.
