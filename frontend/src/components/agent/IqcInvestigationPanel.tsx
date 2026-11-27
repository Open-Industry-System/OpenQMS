import { Alert, Button, Descriptions, Drawer, Select, Space, Spin, Tag } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  iqcInvestigations, type InvestigationEvidence, type InvestigationFacts,
  type InvestigationResult, type InvestigationTask, type InvestigationContext,
} from "../../api/iqcInvestigations";
import { useCapaCredentialIdentity, useCapaViewRequests } from "../capa/useCapaViewRequests";

const READ_INTERVAL = 5000;
const statusOf = (error: unknown) => (error as { response?: { status?: number } })?.response?.status;
const notReadable = (error: unknown) => [401, 403, 404].includes(statusOf(error) ?? 0);
const isId = (value: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

function Facts({ facts }: { facts: InvestigationFacts }) {
  const { t } = useTranslation("iqc", { keyPrefix: "investigation" });
  const fields = [
    ["inspectionNo", facts.inspection_no],
    ["productLine", facts.product_line_code],
    ["status", t(`inspectionStatus.${facts.status}`, { defaultValue: facts.status })],
    ...(facts.prior_inspection_result
      ? [["priorResult", t(`resultStatus.${facts.prior_inspection_result}`)] as const]
      : []),
    ["result", t(`resultStatus.${facts.inspection_result}`, { defaultValue: facts.inspection_result })],
    ["part", [facts.part_no, facts.part_name].filter(Boolean).join(" · ")],
    ["batch", facts.lot_no],
    ["lotQty", facts.lot_qty],
    ["sampleQty", facts.sample_qty],
    ["inspectionDate", facts.inspection_date],
    ["defectQty", facts.defect_qty],
    ["aql", facts.aql_level],
    ["acceptNumber", facts.accept_number],
    ["rejectNumber", facts.reject_number],
    ["observation", facts.defect_description],
  ] as const;
  const family = facts.family.filter(member => member.inspection_id !== facts.inspection_id);

  return <>
    <Descriptions size="small" column={1}>
      {fields.map(([key, value]) => (
        <Descriptions.Item key={key} label={t(`fact.${key}`)}>
          {value === "" || value == null ? "—" : value}
        </Descriptions.Item>
      ))}
    </Descriptions>
    {!!family.length && <section>
      <h5>{t("relatedInspections")}</h5>
      <ul>{family.map(member => <li key={member.inspection_id}>
        {member.inspection_no} · {member.inspection_date ?? "—"} ·{" "}
        {t(`resultStatus.${member.inspection_result}`, { defaultValue: member.inspection_result })}
      </li>)}</ul>
    </section>}
    {facts.disposition_changed && <p>{t("dispositionChanged")}</p>}
    {!facts.family_complete && <p>{t("familyIncomplete")}</p>}
  </>;
}

const evidenceFields = [
  "inspection_no", "inspection_date", "item_name", "inspection_result", "inspect_type", "result",
  "spec_lower", "spec_upper", "target_value", "sample_size", "aql_level", "accept_number", "reject_number",
  "sequence_no", "measured_value", "attribute_result", "remark", "defect_qty", "part_no", "part_name",
  "supplier_no", "name", "number", "status",
] as const;

function evidenceRows(data: unknown): Record<string, unknown>[] {
  let input: unknown[] = [data];
  if (Array.isArray(data)) input = data;
  else if (typeof data === "object" && data !== null) {
    for (const key of ["rows", "items", "investigations"] as const) {
      const rows = (data as Record<string, unknown>)[key];
      if (Array.isArray(rows)) {
        input = rows;
        break;
      }
    }
  }
  return input.filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null);
}

function Evidence({ evidence }: { evidence: InvestigationEvidence }) {
  const { t } = useTranslation("iqc", { keyPrefix: "investigation" });
  const rows = evidenceRows(evidence.data);
  return <details>
    <summary>{t(`projection.${evidence.projection}`, { defaultValue: evidence.projection })}</summary>
    <p>{t("evidenceVersion", { version: evidence.version })}</p>
    {rows.map((row, index) => <Descriptions key={index} size="small" column={1}>
      {evidenceFields.map(field => {
        const value = row[field];
        return typeof value === "string" || typeof value === "number"
          ? <Descriptions.Item key={field} label={t(`evidenceField.${field}`)}>{value}</Descriptions.Item>
          : null;
      })}
    </Descriptions>)}
  </details>;
}

function ActionHint({ hint }: { hint: InvestigationResult["current_hint"] }) {
  const { t } = useTranslation("iqc", { keyPrefix: "investigation" });
  return <section>
    <h4>{t("currentAction")}</h4>
    <p>{t(`action.${hint.action}`)}</p>
    {!!hint.checked_modules.length && <p>{t("reviewedScope", {
      modules: hint.checked_modules.map(module => t(`module.${module}`, { defaultValue: module })).join(" · "),
    })}</p>}
    {!!hint.investigations.length && <ul>{hint.investigations.map(item => {
      const root = item.kind === "capa" ? "/capa/" : item.kind === "scar" ? "/scars/" : null;
      const href = root && isId(item.object_id) ? `${root}${item.object_id}` : null;
      const name = `${t(`module.${item.kind}`)} · ${item.number}`;
      return <li key={`${item.kind}/${item.object_id}`}>
        {href ? <Link to={href}>{name}</Link> : name} {item.status && <Tag>{item.status}</Tag>}
        {item.summary && <p>{item.summary}</p>}
      </li>;
    })}</ul>}
  </section>;
}

function ResultCard({ inspectionId, taskId, resultId, scopeKey, credentialsCurrent }: {
  inspectionId: string; taskId: string; resultId: string; scopeKey: string; credentialsCurrent: () => boolean;
}) {
  const { t } = useTranslation("iqc", { keyPrefix: "investigation" });
  const requests = useCapaViewRequests(scopeKey, credentialsCurrent);
  const [view, setView] = useState<InvestigationResult | null>();
  const [copyState, setCopyState] = useState<"copying" | "copied" | "failed">();
  const copyLock = useRef(false);
  const withdrawn = useRef(false);

  const read = useCallback(async (signal: AbortSignal) => {
    const value = await iqcInvestigations.result(inspectionId, taskId, resultId, signal);
    if (value.task_id !== taskId || value.result_id !== resultId || value.card.facts.inspection_id !== inspectionId) {
      throw new Error("Unexpected IQC investigation result");
    }
    return value;
  }, [inspectionId, resultId, taskId]);

  useEffect(() => {
    const request = requests.begin();
    let timer: ReturnType<typeof setTimeout> | undefined;
    withdrawn.current = false;
    async function refresh() {
      if (!request.current() || withdrawn.current) return;
      try {
        const value = await read(request.signal);
        if (request.current() && !withdrawn.current) {
          setView(value);
          timer = setTimeout(refresh, READ_INTERVAL);
        }
      } catch {
        if (request.current()) {
          withdrawn.current = true;
          setView(null);
        }
      }
    }
    void refresh();
    return () => {
      request.cancel();
      clearTimeout(timer);
    };
  }, [read, requests]);

  async function copyD2() {
    if (copyLock.current || withdrawn.current) return;
    const request = requests.begin();
    if (!request.current()) return;
    copyLock.current = true;
    setCopyState("copying");
    try {
      const latest = await read(request.signal);
      if (!request.current() || withdrawn.current) return;
      setView(latest);
      if (!latest.card.d2) {
        setCopyState("failed");
        return;
      }
      await navigator.clipboard.writeText(latest.card.d2);
      if (request.current() && !withdrawn.current) setCopyState("copied");
    } catch (error) {
      if (request.current()) {
        if (notReadable(error)) {
          withdrawn.current = true;
          setView(null);
        } else setCopyState("failed");
      }
    } finally {
      copyLock.current = false;
      request.finish();
    }
  }

  if (view === undefined) return <Spin size="small" aria-label={t("loading")} />;
  if (!view) return <Alert type="warning" message={t("unavailable")} />;
  const { card } = view;
  return <section aria-label={t("resultCard")}>
    <h4>{t("resultCard")}</h4>
    <p>{t("createdAt", { value: new Date(view.created_at).toLocaleString() })}</p>
    <p>{t("basisRevision", { revision: card.facts.inspection_revision })}
      {view.model_deployment && ` · ${view.model_deployment.name} · ${view.model_deployment.version}`}
    </p>
    {view.stale && <Alert type="warning" message={t("stale")} showIcon />}
    <h5>{t("confirmed")}</h5>
    <Facts facts={card.facts} />
    <h5>{t("missing")}</h5>
    {card.missing.length ? <ul>{card.missing.map(code => <li key={code}>{t(`gap.${code}`)}</li>)}</ul> : <p>{t("noGaps")}</p>}
    <h5>{t("nextSteps")}</h5>
    {!!card.next_steps.length && <ul>{card.next_steps.map(code => <li key={code}>{t(`step.${code}`)}</li>)}</ul>}
    <p>{t("originalAction", { action: t(`action.${card.action}`) })}</p>
    <ActionHint hint={view.current_hint} />
    <h5>{t("d2")}</h5>
    {card.d2
      ? <>
        <p style={{ whiteSpace: "pre-wrap" }}>{card.d2}</p>
        <Button onClick={() => void copyD2()} loading={copyState === "copying"}>{t("copy")}</Button>
        {copyState === "copied" && <p role="status">{t("copied")}</p>}
        {copyState === "failed" && <p role="alert">{t("copyFailed")}</p>}
      </>
      : <p>{t("d2Unavailable")}</p>}
    {!!card.evidence.length && <section>
      <h5>{t("evidence")}</h5>
      {card.evidence.map(item => <Evidence key={item.receipt_id} evidence={item} />)}
    </section>}
  </section>;
}

export function IqcInvestigationPanel({ inspectionId, scopeKey, credentialsCurrent }: {
  inspectionId: string; scopeKey: string; credentialsCurrent: () => boolean;
}) {
  const { t } = useTranslation("iqc", { keyPrefix: "investigation" });
  const requests = useCapaViewRequests(scopeKey, credentialsCurrent);
  const [context, setContext] = useState<InvestigationContext | null>();
  const [tasks, setTasks] = useState<InvestigationTask[] | null>();
  const [deploymentId, setDeploymentId] = useState<string>();
  const [selectedResult, setSelectedResult] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<"versionChanged" | "requestFailed">();
  const [reload, setReload] = useState(0);
  const busy = useRef(false);
  const [controlBusy, setControlBusy] = useState(false);
  const controlledTask = useRef<string>();
  const attempt = useRef<{ fingerprint: string; key: string }>();
  const desiredTask = useRef<string>();

  useEffect(() => {
    const request = requests.begin();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setContext(undefined);
    async function readContext() {
      try {
        const value = await iqcInvestigations.context(inspectionId, request.signal);
        if (request.current() && value.inspection_id === inspectionId) {
          setContext(value);
          setDeploymentId(prior => value.deployments.some(item => item.deployment_id === prior)
            ? prior : value.deployments[0]?.deployment_id);
        } else if (request.current()) setContext(null);
      } catch {
        if (request.current()) setContext(null);
      }
    }
    async function list() {
      try {
        const page = await iqcInvestigations.list(inspectionId, request.signal);
        if (request.current()) {
          setTasks(page.items);
          const readyResult = page.items.find(task => task.task_id === desiredTask.current && task.result_id);
          if (readyResult?.result_id) {
            desiredTask.current = undefined;
            setSelectedResult(readyResult.result_id);
          }
          const active = page.items.some(task => ["ready", "queued", "running", "active"].includes(task.status));
          if (active || busy.current || page.items.length) {
            // Completed rows still inherit source authority while history is visible.
            timer = setTimeout(list, active || busy.current ? READ_INTERVAL : READ_INTERVAL * 2);
          }
        }
      } catch {
        if (request.current()) {
          setTasks(null);
          setSelectedResult(undefined);
        }
      }
    }
    void readContext();
    void list();
    return () => {
      request.cancel();
      clearTimeout(timer);
    };
  }, [inspectionId, reload, requests]);

  const result = tasks?.find(task => task.result_id === selectedResult);

  async function submit(previousResultId?: string, existingTaskId?: string) {
    if (busy.current || (!existingTaskId && (!context?.eligible || !deploymentId))) return;
    const request = requests.begin();
    if (!request.current()) return;
    busy.current = true;
    setLoading(true);
    setNotice(undefined);
    try {
      let taskId = existingTaskId;
      let state = "ready";
      if (!taskId && context && deploymentId) {
        const fingerprint = JSON.stringify([context.expected_version, deploymentId, previousResultId ?? null]);
        if (attempt.current?.fingerprint !== fingerprint) {
          attempt.current = { fingerprint, key: crypto.randomUUID() };
        }
        const task = await iqcInvestigations.create(inspectionId, {
          expected_version: context.expected_version,
          request_key: attempt.current.key,
          model_deployment_id: deploymentId,
          ...(previousResultId ? { previous_result_id: previousResultId } : {}),
        }, request.signal);
        taskId = task.task_id;
        state = task.status;
      }
      if (!taskId || !request.current()) return;
      desiredTask.current = taskId;
      controlledTask.current = undefined;
      setReload(value => value + 1);
      if (state === "ready") await iqcInvestigations.launch(inspectionId, taskId, request.signal);
      if (request.current()) attempt.current = undefined;
    } catch (error) {
      if (!request.current() || (desiredTask.current && controlledTask.current === desiredTask.current)) return;
      if (statusOf(error) === 409) {
        attempt.current = undefined;
        setNotice("versionChanged");
      } else if (notReadable(error)) {
        setContext(null);
        setTasks(null);
        setSelectedResult(undefined);
      } else setNotice("requestFailed");
    } finally {
      if (request.current()) {
        setLoading(false);
        setReload(value => value + 1);
      }
      busy.current = false;
      request.finish();
    }
  }

  async function control(taskId: string, operation: "pause" | "resume" | "cancel") {
    if (controlBusy) return;
    const request = requests.begin();
    if (!request.current()) return;
    setControlBusy(true);
    try {
      await iqcInvestigations.control(inspectionId, taskId, operation, request.signal);
      if (request.current()) controlledTask.current = taskId;
    } catch {
      if (request.current()) setNotice("requestFailed");
    } finally {
      if (request.current()) {
        setControlBusy(false);
        setReload(value => value + 1);
      }
      request.finish();
    }
  }

  return <Space direction="vertical" size="middle" style={{ width: "100%" }}>
    {notice && <Alert type="warning" message={t(notice)} showIcon />}
    {context === undefined ? <Spin size="small" aria-label={t("loading")} /> : context === null
      ? <Alert type="info" message={t("unavailable")} />
      : <>
        <Space wrap>
          <span>{t("scope", { number: context.facts.inspection_no })}</span>
          <Tag>{t(`inspectionStatus.${context.facts.status}`, { defaultValue: context.facts.status })}</Tag>
          <Tag>{t(`resultStatus.${context.facts.inspection_result}`, { defaultValue: context.facts.inspection_result })}</Tag>
        </Space>
        {context.eligible && !!context.deployments.length && <Space wrap>
          <Select aria-label={t("deployment")} value={deploymentId}
            onChange={setDeploymentId} disabled={loading}
            options={context.deployments.map(item => ({ value: item.deployment_id, label: `${item.name} · ${item.version}` }))}
            style={{ minWidth: 190 }} />
          <Button type="primary" aria-label={t(result ? "regenerate" : "prepare")}
            onClick={() => void submit(result?.result_id ?? undefined)} loading={loading} disabled={!deploymentId}>
            {t(result ? "regenerate" : "prepare")}
          </Button>
        </Space>}
        {context.eligible && !context.deployments.length && <p>{t("noDeployments")}</p>}
        {!context.eligible && <p>{context.eligibility_reason ? t(`eligibility.${context.eligibility_reason}`) : t("ineligible")}</p>}
      </>}
    {!!tasks?.length && <section>
      <h4>{t("history")}</h4>
      <ul>{tasks.map(task => <li key={task.task_id}>
        <Space wrap>
          {task.created_at && <span>{new Date(task.created_at).toLocaleString()}</span>}
          <Tag>{t(`taskStatus.${task.status}`, { defaultValue: task.status })}</Tag>
          {task.result_id && <Button onClick={() => {
            desiredTask.current = undefined;
            setSelectedResult(task.result_id ?? undefined);
          }}>{t("openResult")}</Button>}
          {task.status === "ready" && context?.eligible && <Button disabled={loading}
            onClick={() => void submit(undefined, task.task_id)}>{t("launch")}</Button>}
          {task.status === "running" && <Button disabled={controlBusy}
            onClick={() => void control(task.task_id, "pause")}>{t("pause")}</Button>}
          {task.status === "paused" && context?.eligible && <Button disabled={controlBusy}
            onClick={() => void control(task.task_id, "resume")}>{t("resume")}</Button>}
          {["ready", "running", "paused"].includes(task.status) && <Button disabled={controlBusy}
            onClick={() => void control(task.task_id, "cancel")}>{t("cancel")}</Button>}
        </Space>
      </li>)}</ul>
    </section>}
    {tasks === null && <Alert type="warning" message={t("historyUnavailable")} />}
    {result?.result_id && <ResultCard key={`${result.task_id}/${result.result_id}`}
      inspectionId={inspectionId} taskId={result.task_id} resultId={result.result_id}
      scopeKey={scopeKey} credentialsCurrent={credentialsCurrent} />}
  </Space>;
}

function ScopedDrawer({ inspectionId, scopeKey, credentialsCurrent }: {
  inspectionId: string; scopeKey: string; credentialsCurrent: () => boolean;
}) {
  const { t } = useTranslation("iqc", { keyPrefix: "investigation" });
  const [open, setOpen] = useState(false);
  return <>
    <Button onClick={() => setOpen(true)}>{t("title")}</Button>
    <Drawer title={t("title")} open={open} onClose={() => setOpen(false)} width={600}>
      {open && <IqcInvestigationPanel inspectionId={inspectionId} scopeKey={scopeKey}
        credentialsCurrent={credentialsCurrent} />}
    </Drawer>
  </>;
}

export default function IqcInvestigationDrawer({ inspectionId }: { inspectionId: string }) {
  const { identity, current } = useCapaCredentialIdentity();
  const scopeKey = JSON.stringify([identity, inspectionId]);
  return <ScopedDrawer key={scopeKey} inspectionId={inspectionId} scopeKey={scopeKey} credentialsCurrent={current} />;
}
