# OpenQMS Public Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public, bilingual OpenQMS landing page at `/` that presents AI as the core product differentiator, links to the real open-source repository, and optionally exposes a configuration-gated Viewer demo login.

**Architecture:** Keep the public site inside the existing React/Vite application. A lazy `PublicHomePage` renders entirely from static i18n resources and scoped CSS, while the existing `/dashboard` and business routes remain under `ProtectedRoute`. A small pure config reader is the single source of truth for whether public demo credentials are complete and enabled; both the home page and login page consume it.

**Tech Stack:** React 18, TypeScript 5.6, Vite 5.4, React Router 6, Ant Design 5, i18next/react-i18next, Vitest, Testing Library, CSS

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-09-09-openqms-public-home-design.md`.
- `/` is always public, including for authenticated users; `/dashboard` and all business routes stay protected.
- Use the approved dark knowledge-graph visual direction: deep navy background, cyan-green accent, restrained grid/node effects.
- AI is the first major content section after the hero and must explain context, retrieval, generation, human review, provenance, permissions, isolation, and auditability.
- Public copy must describe IATF 16949 process coverage, never claim third-party certification.
- Chinese (`zh-CN`) is canonical and English (`en-US`) must have the same translation structure.
- Do not add state management, animation, icon, styling, analytics, or content-management dependencies.
- The page must work without backend API availability.
- Viewer demo is disabled by default and is enabled only when all three Vite variables are valid.
- This iteration must not expose Engineer, Manager, Admin, or real-environment credentials.
- Demo credential fill is explicit user action and must never auto-submit the form.
- Desktop shows all anchor links; narrow screens hide anchor links and retain only language and system-entry actions—no hamburger-menu state.
- Decorative graph elements are `aria-hidden`; animation obeys `prefers-reduced-motion`.
- Update README, deployment documentation, and `PROGRESS.md` because `frontend/src/` and `docker-compose.yml` change.
- Before implementing the visual page in Task 3, load and follow `frontend-design:frontend-design`.

## File Structure

### Create

- `frontend/src/config/publicDemo.ts` — parse and validate the three public-demo Vite variables.
- `frontend/src/config/publicDemo.test.ts` — pure unit tests for disabled, incomplete, and enabled config.
- `frontend/src/locales/zh-CN/home.json` — canonical Chinese public-home content.
- `frontend/src/locales/en-US/home.json` — structurally identical English content.
- `frontend/src/locales/home.i18n.test.ts` — enforce locale shape and load-bearing array lengths.
- `frontend/src/pages/public/PublicHomePage.tsx` — semantic public landing-page structure and routing links.
- `frontend/src/pages/public/PublicHomePage.css` — isolated design tokens, layout, graph decoration, responsive rules, and reduced-motion behavior.
- `frontend/src/pages/public/PublicHomePage.test.tsx` — content, CTA, language, external-link, auth-entry, and demo-visibility tests.
- `frontend/src/App.public-route.test.tsx` — prove `/` is public and `/dashboard` remains protected.
- `frontend/src/pages/login/LoginPage.test.tsx` — prove Viewer demo visibility, one-click fill, no auto-submit, and fail-closed config behavior.

### Modify

- `frontend/src/vite-env.d.ts` — type the three optional `VITE_PUBLIC_DEMO_*` variables.
- `.env.example` — document disabled-by-default demo variables without adding live credentials.
- `docker-compose.yml` — pass optional demo variables to the Vite development container.
- `frontend/src/App.tsx` — lazy-load the public page and move `/` outside the protected layout.
- `frontend/src/pages/login/LoginPage.tsx` — replace the unconditional Admin credential footer with the gated Viewer demo card.
- `frontend/src/locales/zh-CN/login.json` — add Chinese demo-card copy and remove `defaultAccount`.
- `frontend/src/locales/en-US/login.json` — add matching English demo-card copy and remove `defaultAccount`.
- `README.md` — distinguish the public home, login route, and optional Viewer demo.
- `docs/deployment.md` — explain public-demo configuration and security constraints.
- `PROGRESS.md` — record implementation, verification evidence, and next step for multi-role demo infrastructure.

---

### Task 1: Public Demo Configuration Contract

**Files:**
- Create: `frontend/src/config/publicDemo.ts`
- Create: `frontend/src/config/publicDemo.test.ts`
- Modify: `frontend/src/vite-env.d.ts:1`
- Modify: `.env.example:1-4`
- Modify: `docker-compose.yml:47-59`

**Interfaces:**
- Consumes: Vite's `ImportMetaEnv` and string environment values.
- Produces: `PublicDemoConfig`, `PublicDemoEnv`, and `getPublicDemoConfig(env?: PublicDemoEnv): PublicDemoConfig | null`.
- Later tasks call `getPublicDemoConfig()` during render; tests pass an explicit plain object.

- [ ] **Step 1: Write the failing config tests**

Create `frontend/src/config/publicDemo.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { getPublicDemoConfig } from "./publicDemo";

describe("getPublicDemoConfig", () => {
  it("is disabled unless the flag is exactly true", () => {
    expect(getPublicDemoConfig({
      VITE_PUBLIC_DEMO_ENABLED: "false",
      VITE_PUBLIC_DEMO_USERNAME: "viewer",
      VITE_PUBLIC_DEMO_PASSWORD: "demo-test-password",
    })).toBeNull();
  });

  it.each([
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "", VITE_PUBLIC_DEMO_PASSWORD: "demo-test-password" },
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "viewer", VITE_PUBLIC_DEMO_PASSWORD: "" },
    { VITE_PUBLIC_DEMO_ENABLED: "true", VITE_PUBLIC_DEMO_USERNAME: "viewer", VITE_PUBLIC_DEMO_PASSWORD: "   " },
  ])("fails closed when credentials are incomplete", (env) => {
    expect(getPublicDemoConfig(env)).toBeNull();
  });

  it("returns trimmed username and the original password when fully configured", () => {
    expect(getPublicDemoConfig({
      VITE_PUBLIC_DEMO_ENABLED: "true",
      VITE_PUBLIC_DEMO_USERNAME: " viewer ",
      VITE_PUBLIC_DEMO_PASSWORD: "demo-test-password",
    })).toEqual({ username: "viewer", password: "demo-test-password" });
  });
});
```

- [ ] **Step 2: Run the config test to verify RED**

Run:

```bash
cd frontend && npm test -- --run src/config/publicDemo.test.ts
```

Expected: FAIL because `./publicDemo` does not exist.

- [ ] **Step 3: Implement the pure config reader**

Create `frontend/src/config/publicDemo.ts`:

```ts
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
```

Append the explicit optional fields to `frontend/src/vite-env.d.ts`:

```ts
interface ImportMetaEnv {
  readonly VITE_PUBLIC_DEMO_ENABLED?: string;
  readonly VITE_PUBLIC_DEMO_USERNAME?: string;
  readonly VITE_PUBLIC_DEMO_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

- [ ] **Step 4: Propagate disabled-by-default values through local Docker configuration**

Append to `.env.example`:

```dotenv
# Public Viewer demo. These values are embedded in the browser bundle when enabled.
VITE_PUBLIC_DEMO_ENABLED=false
VITE_PUBLIC_DEMO_USERNAME=
VITE_PUBLIC_DEMO_PASSWORD=
```

Add these entries under `services.frontend.environment` in `docker-compose.yml`:

```yaml
      VITE_PUBLIC_DEMO_ENABLED: ${VITE_PUBLIC_DEMO_ENABLED:-false}
      VITE_PUBLIC_DEMO_USERNAME: ${VITE_PUBLIC_DEMO_USERNAME:-}
      VITE_PUBLIC_DEMO_PASSWORD: ${VITE_PUBLIC_DEMO_PASSWORD:-}
```

Do not put `demo-test-password` in `.env.example` or `docker-compose.yml`; enabling the public demo must be deliberate.

- [ ] **Step 5: Run config tests and TypeScript build**

Run:

```bash
cd frontend && npm test -- --run src/config/publicDemo.test.ts && npm run build
```

Expected: 5 config test executions PASS and the production build exits 0.

- [ ] **Step 6: Commit the config contract**

```bash
git add frontend/src/config/publicDemo.ts frontend/src/config/publicDemo.test.ts frontend/src/vite-env.d.ts .env.example docker-compose.yml
git commit -m "feat(frontend): add gated public demo config"
```

---

### Task 2: Bilingual Public-Home Content Contract

**Files:**
- Create: `frontend/src/locales/zh-CN/home.json`
- Create: `frontend/src/locales/en-US/home.json`
- Create: `frontend/src/locales/home.i18n.test.ts`

**Interfaces:**
- Consumes: the existing eager `import.meta.glob("../locales/**/*.json")` loader in `frontend/src/i18n/index.ts`; no loader edit is needed.
- Produces: the `home` namespace with arrays of exactly 4 metrics, 4 AI stages, 4 AI use cases, 6 trust labels, 6 capability groups, and 7 technology labels.
- Task 3 reads object arrays through `t(key, { returnObjects: true })`.

- [ ] **Step 1: Write the failing locale-parity test**

Create `frontend/src/locales/home.i18n.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import zh from "./zh-CN/home.json";
import en from "./en-US/home.json";

function shape(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(shape);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, child]) => [key, shape(child)]),
    );
  }
  return typeof value;
}

describe("home i18n contract", () => {
  it("keeps Chinese and English structures identical", () => {
    expect(shape(en)).toEqual(shape(zh));
  });

  it("keeps the approved section cardinalities", () => {
    for (const locale of [zh, en]) {
      expect(locale.metrics).toHaveLength(4);
      expect(locale.ai.stages).toHaveLength(4);
      expect(locale.ai.useCases).toHaveLength(4);
      expect(locale.ai.trust).toHaveLength(6);
      expect(locale.capabilities.items).toHaveLength(6);
      expect(locale.architecture.stack).toHaveLength(7);
    }
  });
});
```

- [ ] **Step 2: Run the locale test to verify RED**

Run:

```bash
cd frontend && npm test -- --run src/locales/home.i18n.test.ts
```

Expected: FAIL because both `home.json` files are absent.

- [ ] **Step 3: Add the canonical Chinese content**

Create `frontend/src/locales/zh-CN/home.json` with this exact shape and approved copy:

```json
{
  "nav": {
    "ai": "AI 质量智能",
    "capabilities": "核心能力",
    "architecture": "技术架构",
    "openSource": "开源社区",
    "enterSystem": "进入系统"
  },
  "hero": {
    "eyebrow": "AI-NATIVE QUALITY MANAGEMENT",
    "title": "让质量数据，转化为可执行智能。",
    "description": "OpenQMS 将 AI 嵌入 FMEA、8D、过程分析与知识复用流程，让质量工程师更快发现风险、验证原因并沉淀经验。",
    "demo": "在线体验",
    "login": "进入系统",
    "github": "查看 GitHub",
    "graphLabel": "质量智能核心",
    "graphNodes": ["FMEA 风险", "SPC 过程", "8D 闭环", "供应商质量", "知识图谱"]
  },
  "metrics": [
    { "value": "20+", "label": "质量模块" },
    { "value": "AIAG-VDA", "label": "七步法" },
    { "value": "IATF 16949", "label": "核心流程覆盖" },
    { "value": "MIT", "label": "开源许可" }
  ],
  "ai": {
    "eyebrow": "HOW AI WORKS IN OPENQMS",
    "title": "AI 是质量工程师的副驾驶，不是黑盒决策者",
    "description": "系统先从质量上下文中检索事实，再融合生成建议，由人确认后写入业务流程。每条建议保留来源、置信度和审计轨迹。",
    "stages": [
      { "index": "01 · CONTEXT", "title": "连接质量上下文", "body": "FMEA、CAPA、SPC、IQC、MES、供应商与经验库" },
      { "index": "02 · RETRIEVAL", "title": "多路径知识召回", "body": "知识图谱、语义搜索、规则引擎与历史案例" },
      { "index": "03 · REASONING", "title": "融合与生成建议", "body": "候选去重、排序、上下文增强与 LLM 结构化输出" },
      { "index": "04 · GOVERNANCE", "title": "人工确认并留痕", "body": "权限门禁、人工审批、来源标签与审计日志" }
    ],
    "useCases": [
      { "title": "FMEA 智能推荐", "body": "辅助补全功能、失效、原因、控制措施与优化行动。" },
      { "title": "8D 根因与措施", "body": "以 12 阶段编排多类质量数据，提供可解释候选建议。" },
      { "title": "质量知识问答", "body": "RAG 混合检索历史文档和节点，并按权限范围返回答案。" },
      { "title": "趋势解读与草拟", "body": "辅助解释质量趋势，生成 8D 步骤和管理评审内容草稿。" }
    ],
    "trust": ["来源可见", "采纳可审计", "工厂数据隔离", "权限范围约束", "输入 / 输出 Guardrails", "多 Provider 配置"],
    "principleLabel": "核心原则",
    "principle": "AI 不绕过业务规则，也不替代工程师审批；它把分散在系统里的质量知识带到决策现场。"
  },
  "capabilities": {
    "eyebrow": "CONNECTED QUALITY SYSTEM",
    "title": "AI 之下，是完整的质量业务闭环",
    "items": [
      { "title": "风险与策划", "body": "FMEA · APQP · PPAP · 控制计划" },
      { "title": "过程与测量", "body": "SPC · MSA · IQC · 特殊特性" },
      { "title": "问题与改进", "body": "8D/CAPA · SCAR · 客诉 · RMA" },
      { "title": "供应链质量", "body": "供应商绩效 · 风险预警 · 客户质量" },
      { "title": "治理与合规", "body": "审计 · 管理评审 · RBAC · 多工厂" },
      { "title": "开放集成", "body": "ERP · MES · PLM · API" }
    ]
  },
  "architecture": {
    "eyebrow": "MODERN OPEN ARCHITECTURE",
    "title": "可部署、可扩展，也可持续演进",
    "description": "关系数据保持事务与审计，图数据支撑知识关联，AI 服务通过可配置 Provider 接入。",
    "stack": ["React + TypeScript", "FastAPI", "SQLAlchemy", "PostgreSQL", "Neo4j", "Redis", "Docker Compose"]
  },
  "openSource": {
    "eyebrow": "BUILT IN THE OPEN",
    "title": "从源码开始，构建你的质量系统",
    "description": "查看源代码和部署文档，或使用 Viewer 只读账号体验完整质量流程。",
    "github": "查看 GitHub",
    "docs": "阅读项目文档",
    "demo": "进入演示系统"
  },
  "footer": {
    "license": "OpenQMS · MIT License",
    "tagline": "面向制造业的开源质量管理平台"
  }
}
```

- [ ] **Step 4: Add the English mirror**

Create `frontend/src/locales/en-US/home.json` with this complete mirror:

```json
{
  "nav": {
    "ai": "AI quality intelligence",
    "capabilities": "Core capabilities",
    "architecture": "Architecture",
    "openSource": "Open source",
    "enterSystem": "Enter system"
  },
  "hero": {
    "eyebrow": "AI-NATIVE QUALITY MANAGEMENT",
    "title": "Turn quality data into actionable intelligence.",
    "description": "OpenQMS embeds AI into FMEA, 8D, process analysis, and knowledge reuse so quality engineers can identify risk, validate causes, and retain experience faster.",
    "demo": "Online demo",
    "login": "Enter system",
    "github": "View GitHub",
    "graphLabel": "Quality AI core",
    "graphNodes": ["FMEA risk", "SPC process", "8D closure", "Supplier quality", "Knowledge graph"]
  },
  "metrics": [
    { "value": "20+", "label": "Quality modules" },
    { "value": "AIAG-VDA", "label": "Seven-step method" },
    { "value": "IATF 16949", "label": "Core process coverage" },
    { "value": "MIT", "label": "Open-source license" }
  ],
  "ai": {
    "eyebrow": "HOW AI WORKS IN OPENQMS",
    "title": "AI is the quality engineer's copilot—not a black-box decision maker.",
    "description": "The system retrieves evidence from quality context, fuses it into suggestions, and writes back only after human confirmation. Every suggestion retains its source, confidence, and audit trail.",
    "stages": [
      { "index": "01 · CONTEXT", "title": "Connect quality context", "body": "FMEA, CAPA, SPC, IQC, MES, supplier data, and lessons learned" },
      { "index": "02 · RETRIEVAL", "title": "Retrieve through multiple paths", "body": "Knowledge graph, semantic search, rule engines, and historical cases" },
      { "index": "03 · REASONING", "title": "Fuse and generate suggestions", "body": "Candidate deduplication, ranking, context enrichment, and structured LLM output" },
      { "index": "04 · GOVERNANCE", "title": "Confirm and audit", "body": "Permission gates, human approval, source labels, and audit logs" }
    ],
    "useCases": [
      { "title": "FMEA recommendations", "body": "Assist with functions, failures, causes, controls, and optimization actions." },
      { "title": "8D causes and actions", "body": "Orchestrate quality data across 12 stages to produce explainable candidates." },
      { "title": "Quality knowledge Q&A", "body": "Use hybrid RAG over historical documents and nodes, scoped by user permissions." },
      { "title": "Trend interpretation and drafting", "body": "Interpret quality trends and draft 8D steps and management-review content." }
    ],
    "trust": ["Visible sources", "Auditable adoption", "Factory data isolation", "Permission-scoped results", "Input / output guardrails", "Multiple providers"],
    "principleLabel": "Core principle",
    "principle": "AI does not bypass business rules or replace engineering approval. It brings quality knowledge from across the system into the decision workflow."
  },
  "capabilities": {
    "eyebrow": "CONNECTED QUALITY SYSTEM",
    "title": "A complete quality loop beneath the AI layer",
    "items": [
      { "title": "Risk and planning", "body": "FMEA · APQP · PPAP · Control plans" },
      { "title": "Process and measurement", "body": "SPC · MSA · IQC · Special characteristics" },
      { "title": "Problems and improvement", "body": "8D/CAPA · SCAR · Complaints · RMA" },
      { "title": "Supply-chain quality", "body": "Supplier performance · Risk alerts · Customer quality" },
      { "title": "Governance and compliance", "body": "Audits · Management review · RBAC · Multiple factories" },
      { "title": "Open integrations", "body": "ERP · MES · PLM · API" }
    ]
  },
  "architecture": {
    "eyebrow": "MODERN OPEN ARCHITECTURE",
    "title": "Deployable, extensible, and built to evolve",
    "description": "Relational data preserves transactions and audit trails, graph data powers knowledge links, and configurable providers connect AI services.",
    "stack": ["React + TypeScript", "FastAPI", "SQLAlchemy", "PostgreSQL", "Neo4j", "Redis", "Docker Compose"]
  },
  "openSource": {
    "eyebrow": "BUILT IN THE OPEN",
    "title": "Start from the source and build your quality system",
    "description": "Explore the source and deployment docs, or use a Viewer account to experience the complete quality workflow.",
    "github": "View GitHub",
    "docs": "Read the docs",
    "demo": "Open demo system"
  },
  "footer": {
    "license": "OpenQMS · MIT License",
    "tagline": "Open-source quality management for manufacturing"
  }
}
```

Retain product names and standards exactly: `OpenQMS`, `FMEA`, `CAPA`, `SPC`, `IQC`, `MES`, `AIAG-VDA`, `IATF 16949`, `RAG`, `LLM`, and `MIT License`.

- [ ] **Step 5: Run locale tests**

Run:

```bash
cd frontend && npm test -- --run src/locales/home.i18n.test.ts
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit the bilingual content contract**

```bash
git add frontend/src/locales/zh-CN/home.json frontend/src/locales/en-US/home.json frontend/src/locales/home.i18n.test.ts
git commit -m "feat(i18n): add public home content"
```

---

### Task 3: Public Home Page and Visual System

**Files:**
- Create: `frontend/src/pages/public/PublicHomePage.tsx`
- Create: `frontend/src/pages/public/PublicHomePage.css`
- Create: `frontend/src/pages/public/PublicHomePage.test.tsx`

**Interfaces:**
- Consumes: `getPublicDemoConfig()`, `useAuthStore((state) => state.token)`, `LanguageSwitcher`, `useTranslation("home")`, React Router `Link`.
- Produces: default export `PublicHomePage` and stable section IDs `ai`, `capabilities`, `architecture`, and `open-source`.
- Task 4 lazy-loads the default export at `/`.

- [ ] **Step 1: Load the frontend visual-design guidance**

Invoke `frontend-design:frontend-design` and apply it within the approved knowledge-graph direction. Do not reopen the product direction or add new dependencies.

- [ ] **Step 2: Write failing public-home component tests**

Create `frontend/src/pages/public/PublicHomePage.test.tsx`. Mock only auth state, not i18n or React Router:

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PublicHomePage from "./PublicHomePage";
import i18n from "../../i18n";

const auth = vi.hoisted(() => ({ token: null as string | null }));
vi.mock("../../store/authStore", () => ({
  useAuthStore: (selector: (state: typeof auth) => unknown) => selector(auth),
}));

function renderPage() {
  return render(<MemoryRouter><PublicHomePage /></MemoryRouter>);
}

beforeEach(async () => {
  auth.token = null;
  vi.unstubAllEnvs();
  await i18n.changeLanguage("en-US");
});

describe("PublicHomePage", () => {
  it("renders the AI-first public narrative and semantic sections", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Turn quality data into actionable intelligence." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /quality engineer's copilot/i })).toBeInTheDocument();
    expect(document.querySelector("main")).toBeInTheDocument();
    expect(document.querySelectorAll("main section")).toHaveLength(5);
    expect(document.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });

  it("uses safe links for the real GitHub repository", () => {
    renderPage();
    const links = screen.getAllByRole("link", { name: /github/i });
    for (const link of links) {
      expect(link).toHaveAttribute("href", "https://github.com/Open-Industry-System/OpenQMS");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    }
  });

  it("hides the demo CTA when demo config is disabled", () => {
    renderPage();
    expect(screen.queryByRole("link", { name: "Online demo" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Enter system" })[0]).toHaveAttribute("href", "/login");
  });

  it("shows a Viewer demo CTA only for complete config", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "viewer");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "demo-test-password");
    renderPage();
    expect(screen.getByRole("link", { name: "Online demo" })).toHaveAttribute("href", "/login?demo=viewer");
  });

  it("sends authenticated users to the dashboard", () => {
    auth.token = "present";
    renderPage();
    expect(screen.getAllByRole("link", { name: "Enter system" })[0]).toHaveAttribute("href", "/dashboard");
  });

  it("switches the visible copy to Chinese", async () => {
    renderPage();
    fireEvent.click(screen.getByText("中文"));
    expect(await screen.findByRole("heading", { name: "让质量数据，转化为可执行智能。" })).toBeInTheDocument();
  });
});
```

If `getAllByRole` returns both header and hero system links, intentionally assert index `0` only after confirming both use the same computed `systemPath`.

- [ ] **Step 3: Run the public-home test to verify RED**

Run:

```bash
cd frontend && npm test -- --run src/pages/public/PublicHomePage.test.tsx
```

Expected: FAIL because `PublicHomePage.tsx` does not exist.

- [ ] **Step 4: Implement the semantic page structure**

In `PublicHomePage.tsx`:

1. Import `Link`, `useTranslation`, `LanguageSwitcher`, `useAuthStore`, `getPublicDemoConfig`, and `./PublicHomePage.css`.
2. Define local TypeScript interfaces for translated `{ value, label }`, `{ index, title, body }`, and `{ title, body }` records.
3. Read translated arrays with `t("metrics", { returnObjects: true })` and equivalent keys, casting only at this JSON boundary.
4. Compute:

```ts
const token = useAuthStore((state) => state.token);
const demoConfig = getPublicDemoConfig();
const systemPath = token ? "/dashboard" : "/login";
const githubUrl = "https://github.com/Open-Industry-System/OpenQMS";
const docsUrl = `${githubUrl}/tree/main/docs`;
```

5. Render this exact semantic hierarchy and class contract:

```text
div.public-home
├── header.public-home__header
│   └── nav[aria-label="OpenQMS"]
│       ├── Link.public-home__brand
│       ├── div.public-home__nav-links
│       └── div.public-home__nav-actions
├── main
│   ├── section.public-home__hero
│   ├── section#ai.public-home__section.public-home__ai
│   ├── section#capabilities.public-home__section
│   ├── section#architecture.public-home__section.public-home__architecture
│   └── section#open-source.public-home__open-source
└── footer.public-home__footer
```

The header brand is `<Link to="/">OpenQMS<span>.</span></Link>`. The four desktop anchor links target `#ai`, `#capabilities`, `#architecture`, and `#open-source`; the nav actions contain `LanguageSwitcher` followed by `<Link to={systemPath}>` using `t("nav.enterSystem")`.

The hero must contain the eyebrow, `h1`, description, conditional demo link, system link, GitHub link, five graph nodes, and the four metric records. The AI section must contain all four stages in order, all four use cases, all six trust labels, and the core-principle callout. Capabilities must render six cards. Architecture must render seven stack labels and a visible flow from React through FastAPI to PostgreSQL/Neo4j. Open source must render GitHub, docs, and conditional demo links.

Every external link must use:

```tsx
target="_blank" rel="noreferrer noopener"
```

The graph wrapper and all purely decorative children must be inside one `aria-hidden="true"` container. Use text and CSS shapes; do not load remote images, videos, or fonts.

- [ ] **Step 5: Implement the scoped visual system**

In `PublicHomePage.css`, define all styles below under `.public-home` or a `.public-home__*` selector:

- Tokens: background `#071520`, elevated background `#0b222d`, primary text `#e7f7f5`, secondary text `#9ab4b7`, accent `#38d4b8`, border `#1e4650`.
- Set `min-height: 100vh`, explicit background, text color, `overflow-x: clip`, and a system sans-serif font stack.
- Sticky translucent header with `backdrop-filter`, a `max-width: 1200px` nav, and visible `:focus-visible` outlines.
- Hero as a two-column grid with a CSS grid background and radial accent glow.
- Graph nodes as positioned pills connected by pseudo-elements or absolutely positioned lines; animation is limited to opacity/transform.
- Metrics as four equal columns beneath the hero.
- AI pipeline as four stage cards with directional connectors; use cases as four cards; trust labels as wrapping pills.
- Capabilities as a three-column card grid and architecture as a two-column panel.
- Open-source CTA centered with a visually distinct border/background.
- At `max-width: 900px`, hide `.public-home__nav-links`, reduce hero to one column, and keep language plus system entry visible.
- At `max-width: 640px`, make metrics two columns and all content-card grids one column; keep buttons wrapping and page width bounded.
- Use `scroll-margin-top` on anchor sections.
- Under `@media (prefers-reduced-motion: reduce)`, disable smooth scrolling, transitions, and graph animations.

Do not style bare `body`, bare `a`, Ant Design global classes, or CSS variables used by the authenticated application.

- [ ] **Step 6: Run the public-home test and build**

Run:

```bash
cd frontend && npm test -- --run src/config/publicDemo.test.ts src/locales/home.i18n.test.ts src/pages/public/PublicHomePage.test.tsx && npm run build
```

Expected: all listed tests PASS and build exits 0.

- [ ] **Step 7: Commit the public page**

```bash
git add frontend/src/pages/public/PublicHomePage.tsx frontend/src/pages/public/PublicHomePage.css frontend/src/pages/public/PublicHomePage.test.tsx
git commit -m "feat(frontend): add AI-first public home"
```

---

### Task 4: Public Root Route Without Auth Regression

**Files:**
- Create: `frontend/src/App.public-route.test.tsx`
- Modify: `frontend/src/App.tsx:1-9,127-143`

**Interfaces:**
- Consumes: Task 3's default `PublicHomePage` export.
- Produces: public route `/`; all existing protected routes remain nested under `<ProtectedRoute><AppLayout /></ProtectedRoute>`.

- [ ] **Step 1: Write the failing route-boundary tests**

Create `frontend/src/App.public-route.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App as AntdApp } from "antd";
import App from "./App";
import i18n from "./i18n";

const state = vi.hoisted(() => ({
  token: null as string | null,
  user: null,
  loading: false,
  login: vi.fn(),
  fetchUser: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("./store/authStore", () => ({
  useAuthStore: (selector: (value: typeof state) => unknown) => selector(state),
}));

vi.mock("./hooks/usePermission", () => ({
  usePermission: () => ({ canView: () => true, isAdmin: false }),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AntdApp><App /></AntdApp>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  state.token = null;
  state.user = null;
  vi.clearAllMocks();
  await i18n.changeLanguage("en-US");
});

describe("public route boundary", () => {
  it("renders the public home at root without authentication", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", {
      name: /turn quality data into actionable intelligence/i,
    })).toBeInTheDocument();
    expect(state.fetchUser).not.toHaveBeenCalled();
  });

  it("still redirects an unauthenticated dashboard request to login", async () => {
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /login/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the route test to verify RED**

Run:

```bash
cd frontend && npm test -- --run src/App.public-route.test.tsx
```

Expected: the root-route assertion FAIL because `/` still redirects through the protected layout.

- [ ] **Step 3: Move only `/` to the public route group**

At the top of `App.tsx`, add:

```ts
const PublicHomePage = lazy(() => import("./pages/public/PublicHomePage"));
```

Inside `<Routes>`, add the root route before `/login`:

```tsx
<Route path="/" element={<PublicHomePage />} />
```

Delete only this existing nested route:

```tsx
<Route path="/" element={<Navigate to="/dashboard" replace />} />
```

Keep the `Navigate` import because `/msa`, `/iqc`, and permission fallbacks still use it. Do not move any other route or change `ProtectedRoute`.

- [ ] **Step 4: Run route and home tests**

Run:

```bash
cd frontend && npm test -- --run src/App.public-route.test.tsx src/pages/public/PublicHomePage.test.tsx
```

Expected: both route-boundary tests and all public-home tests PASS.

- [ ] **Step 5: Commit the route boundary**

```bash
git add frontend/src/App.tsx frontend/src/App.public-route.test.tsx
git commit -m "feat(frontend): expose public root route"
```

---

### Task 5: Configuration-Gated Viewer Demo Login

**Files:**
- Create: `frontend/src/pages/login/LoginPage.test.tsx`
- Modify: `frontend/src/pages/login/LoginPage.tsx:1-15,31-230`
- Modify: `frontend/src/locales/zh-CN/login.json:1-14`
- Modify: `frontend/src/locales/en-US/login.json:1-14`

**Interfaces:**
- Consumes: `getPublicDemoConfig()`, query parameter `demo=viewer`, Ant Design controlled `Form`.
- Produces: a Viewer-only demo card with explicit fill action; normal `/login` has no credentials.

- [ ] **Step 1: Write failing login-demo tests**

Create `frontend/src/pages/login/LoginPage.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App as AntdApp } from "antd";
import LoginPage from "./LoginPage";
import i18n from "../../i18n";

const login = vi.hoisted(() => vi.fn());
vi.mock("../../store/authStore", () => ({
  useAuthStore: (selector: (state: { login: typeof login }) => unknown) => selector({ login }),
}));

function renderLogin(path = "/login?demo=viewer") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AntdApp><LoginPage /></AntdApp>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
  await i18n.changeLanguage("en-US");
});

describe("LoginPage public Viewer demo", () => {
  it("shows no credentials when public demo is disabled", () => {
    renderLogin();
    expect(screen.queryByText("demo-test-password")).not.toBeInTheDocument();
    expect(screen.queryByText(/default account/i)).not.toBeInTheDocument();
  });

  it("fails closed when enabled config is incomplete", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "viewer");
    renderLogin();
    expect(screen.queryByRole("button", { name: /use viewer account/i })).not.toBeInTheDocument();
  });

  it("shows configured Viewer credentials only on the demo route", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "public-readonly-password");
    renderLogin();
    expect(screen.getByText("readonly-demo")).toBeInTheDocument();
    expect(screen.getByText("public-readonly-password")).toBeInTheDocument();
    expect(screen.getByText(/read-only demo/i)).toBeInTheDocument();
  });

  it("fills but does not submit the Viewer credentials", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "public-readonly-password");
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /use viewer account/i }));
    expect(screen.getByPlaceholderText("Username")).toHaveValue("readonly-demo");
    expect(screen.getByPlaceholderText("Password")).toHaveValue("public-readonly-password");
    expect(login).not.toHaveBeenCalled();
  });

  it("does not expose demo credentials on a normal login URL", () => {
    vi.stubEnv("VITE_PUBLIC_DEMO_ENABLED", "true");
    vi.stubEnv("VITE_PUBLIC_DEMO_USERNAME", "readonly-demo");
    vi.stubEnv("VITE_PUBLIC_DEMO_PASSWORD", "public-readonly-password");
    renderLogin("/login");
    expect(screen.queryByText("public-readonly-password")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the login test to verify RED**

Run:

```bash
cd frontend && npm test -- --run src/pages/login/LoginPage.test.tsx
```

Expected: demo-card and fill assertions FAIL; the test also exposes the current unconditional Admin credential footer.

- [ ] **Step 3: Add bilingual login-demo copy**

In both `login.json` files, remove `defaultAccount`. Add this nested object with localized values:

```json
"demo": {
  "title": "Viewer 只读演示",
  "description": "可浏览全部演示模块，无法创建、修改或审批数据。",
  "username": "用户名",
  "password": "密码",
  "fill": "使用 Viewer 账号"
}
```

English values:

```json
"demo": {
  "title": "Viewer read-only demo",
  "description": "Browse all demo modules without creating, editing, or approving data.",
  "username": "Username",
  "password": "Password",
  "fill": "Use Viewer account"
}
```

Preserve every existing non-`defaultAccount` key.

- [ ] **Step 4: Implement the gated demo card and controlled form**

Update imports:

```ts
import { useNavigate, useSearchParams } from "react-router-dom";
import { Form, Input, Button, Typography, App, Alert, Space } from "antd";
import { getPublicDemoConfig } from "../../config/publicDemo";
```

Inside `LoginPage`:

```ts
const [form] = Form.useForm<{ username: string; password: string }>();
const [searchParams] = useSearchParams();
const configuredDemo = getPublicDemoConfig();
const demoConfig = searchParams.get("demo") === "viewer" ? configuredDemo : null;
```

Pass `form={form}` to the existing `<Form>`. Immediately before the form, conditionally render one compact `Alert` or scoped panel containing:

- `t("demo.title")`
- `t("demo.description")`
- visible `demoConfig.username` and `demoConfig.password` in `<Text code>` elements
- a button named `t("demo.fill")`

The fill handler must be exactly equivalent to:

```ts
form.setFieldsValue({
  username: demoConfig.username,
  password: demoConfig.password,
});
```

It must not call `onFinish`, `form.submit()`, or `login`. Delete the unconditional `{t("defaultAccount")}` footer block at current lines 198-210.

- [ ] **Step 5: Run login, config, and home tests**

Run:

```bash
cd frontend && npm test -- --run src/config/publicDemo.test.ts src/pages/login/LoginPage.test.tsx src/pages/public/PublicHomePage.test.tsx src/App.public-route.test.tsx
```

Expected: all tests PASS; no Admin or Viewer password appears on normal `/login`.

- [ ] **Step 6: Commit the Viewer demo login**

```bash
git add frontend/src/pages/login/LoginPage.tsx frontend/src/pages/login/LoginPage.test.tsx frontend/src/locales/zh-CN/login.json frontend/src/locales/en-US/login.json
git commit -m "feat(frontend): add Viewer demo login"
```

---

### Task 6: Documentation, Browser Acceptance, and Full Verification

**Files:**
- Modify: `README.md:82-100`
- Modify: `docs/deployment.md:94-116,162-184`
- Modify: `PROGRESS.md:1-8` and current/next-steps sections

**Interfaces:**
- Consumes: the completed page, route, and demo config from Tasks 1-5.
- Produces: operator-facing instructions, browser verification evidence, and a clean release-quality change set.

- [ ] **Step 1: Update README access instructions**

Change the access section so it states:

```text
http://localhost:5173/        公开项目首页（无需登录）
http://localhost:5173/login   系统登录
http://localhost:5173/dashboard  登录后仪表盘
```

Retain the seed-account table as local development data. Add a note that public deployments must not expose seed credentials and that Viewer demo display is disabled unless explicitly configured.

- [ ] **Step 2: Document Viewer demo deployment configuration**

Add a “公开 Viewer 演示” subsection to `docs/deployment.md` with this exact example:

```dotenv
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer-demo
VITE_PUBLIC_DEMO_PASSWORD=change-me-viewer-demo-only
```

The password shown is an intentionally invalid documentation example, not a repository secret; operators must replace it with the dedicated Viewer demo password. State all of the following:

- The three values are read by Vite and embedded into browser-delivered JavaScript.
- Use only a dedicated Viewer account in a disposable demo environment.
- Never use production, Admin, Manager, or Engineer credentials.
- Missing username or password disables the demo UI even when the flag is `true`.
- Restart/rebuild the frontend after changing Vite variables.
- Multi-role demo requires an isolated tenant, reset automation, write throttling, and dangerous-operation controls and is not enabled by this change.

- [ ] **Step 3: Run focused and full automated checks**

Run:

```bash
cd frontend && npm test -- --run \
  src/config/publicDemo.test.ts \
  src/locales/home.i18n.test.ts \
  src/pages/public/PublicHomePage.test.tsx \
  src/App.public-route.test.tsx \
  src/pages/login/LoginPage.test.tsx
```

Expected: every listed test PASS.

Then run:

```bash
cd frontend && npm run lint && npm run build
```

Expected: lint exits 0 within the repository's existing warning threshold and build exits 0.

Finally run from repository root:

```bash
make check
```

Expected: backend tests, frontend typecheck, and frontend build all exit 0.

- [ ] **Step 4: Verify the real page at desktop and mobile widths**

Use the project `run` skill to start the existing frontend. In a real browser, verify `/` at `1440×900` and `390×844`.

At both widths verify:

- Hero, AI, capabilities, architecture, and open-source sections are readable.
- No authenticated API request is required to render the page.
- `document.documentElement.scrollWidth <= document.documentElement.clientWidth`.
- Desktop displays anchor navigation; mobile hides it while language and system-entry actions remain visible.
- Keyboard Tab reaches language, system, demo (when enabled), GitHub, docs, and footer links with visible focus.
- Chinese/English switching updates the page without reload.
- `/dashboard` while logged out reaches `/login`.
- With demo config disabled, no credential text is present.

Temporarily enable dedicated test-only demo values for the frontend process and verify `/login?demo=viewer` shows the card, fills the form, and does not submit. Do not save those values to a tracked file.

- [ ] **Step 5: Update progress evidence**

Update `PROGRESS.md` with:

- Date `2026-09-09`.
- Public `/` landing page complete.
- AI-first content, bilingual support, and Viewer demo gating complete.
- Exact focused-test counts and `make check` result from Step 3.
- Desktop/mobile browser acceptance result from Step 4.
- Next step: design isolated resettable infrastructure before enabling multi-role public demo.

Do not copy the full design into `PROGRESS.md`; record only status, evidence, and the next actionable step.

- [ ] **Step 6: Inspect the final diff and formatting**

Run:

```bash
git status --short
git diff --check
git diff --stat
git diff -- README.md docs/deployment.md PROGRESS.md
```

Expected: only files named in this plan are changed, `git diff --check` has no output, and docs accurately describe the implemented behavior.

- [ ] **Step 7: Commit documentation and verification evidence**

```bash
git add README.md docs/deployment.md PROGRESS.md
git commit -m "docs: document public home and Viewer demo"
```

- [ ] **Step 8: Request final code review**

Invoke `superpowers:requesting-code-review` over the complete branch diff. Address only verified findings that trace to this approved design, rerun the affected tests, and finish with `superpowers:verification-before-completion` before reporting completion.
