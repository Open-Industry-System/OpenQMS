import { Alert, Button, Spin, Tag } from "antd";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export type ImpactConclusion = "impact_found" | "no_impact_found" | "insufficient_evidence";
export type ImpactTaskStatus =
  | "blocked_capability" | "ready" | "queued" | "running" | "paused"
  | "completed" | "failed" | "cancelled";

export interface ImpactTarget {
  fmeaId: string;
  documentNo: string;
  title: string;
  approvedVersionId: string;
  approvedVersionLabel: string;
  hasUnapprovedRevision: boolean;
}

export interface ImpactTaskStatusView {
  taskId: string;
  status: ImpactTaskStatus;
  resultId?: string | null;
}

export interface ImpactOption {
  installationId: string;
  deploymentId: string;
  name: string;
  version: string;
  kind: "local" | "cloud";
}

export interface ImpactResultChoice {
  taskId: string;
  resultId: string;
  approvedVersionLabel: string;
  freshness: "current" | "stale";
  createdAt: string;
}

interface ImpactMeasureReview {
  measureId: string;
  formalRevision: string | null;
  text: string;
  conclusion: ImpactConclusion;
  facts: readonly string[];
  inference?: string;
  reason: string;
  adjustments: readonly string[];
  gaps: readonly string[];
  evidence: readonly { id: string; label: string }[];
}

export interface ImpactRecommendation {
  reportVersionLabel: string;
  approvedVersionLabel: string;
  freshness: "current" | "stale";
  conclusion: ImpactConclusion;
  measures: readonly ImpactMeasureReview[];
}

type Unavailable = null;
type Evidence = { label: string; text: string };
type ReadinessReason = "d4_not_verified" | "d5_not_adopted" | "sources_unavailable" | "too_large";
type StatusMessage = "unavailable" | "retry" | "versionChanged" | `readiness.${ReadinessReason}`;

export interface PfmeaImpactClients {
  listTargets: (
    reportId: string, options: { page: number; pageSize: number }, signal: AbortSignal,
  ) => Promise<{ items: readonly ImpactTarget[]; total: number } | Unavailable>;
  listOptions?: (
    reportId: string, target: ImpactTarget, signal: AbortSignal,
  ) => Promise<readonly ImpactOption[] | Unavailable>;
  readTask?: (reportId: string, taskId: string, signal: AbortSignal) => Promise<ImpactTaskStatusView | Unavailable>;
  launch?: (reportId: string, taskId: string, signal: AbortSignal) => Promise<ImpactTaskStatusView | Unavailable>;
  cancel?: (reportId: string, taskId: string, signal: AbortSignal) => Promise<ImpactTaskStatusView | Unavailable>;
  listResults?: (
    reportId: string, options: { page: number; pageSize: number }, signal: AbortSignal,
  ) => Promise<{ items: readonly ImpactResultChoice[]; hasMore: boolean } | Unavailable>;
  /** A 409 response means the input changed and must be confirmed again. */
  start: (
    reportId: string,
    input: {
      fmeaId: string; approvedVersionId: string; requestKey: string; installationId?: string; deploymentId?: string;
      previousResultId?: string;
    },
    signal: AbortSignal,
  ) => Promise<ImpactTaskStatusView | Unavailable>;
  readRecommendation: (
    reportId: string, recommendationId: string, signal: AbortSignal,
  ) => Promise<ImpactRecommendation | Unavailable>;
  readEvidence?: (
    reportId: string, recommendationId: string, evidenceId: string, signal: AbortSignal,
  ) => Promise<Evidence | Unavailable>;
}

interface Props {
  reportId: string;
  /** A non-secret identifier that changes with the tenant, viewer or credential. */
  scopeKey: string;
  /** The host increments this when it invalidates previously authorized views. */
  authorityEpoch?: number;
  open?: boolean;
  canGenerate?: boolean;
  client: PfmeaImpactClients;
  recommendationId?: string;
  activeTask?: ImpactTaskStatusView;
  onStarted?: (task: ImpactTaskStatusView) => void;
  /** Scope-owned keys for hosts that unmount closed drawers. */
  requestKeyStore?: Map<string, string>;
}

function useAbortScope() {
  const pool = useRef(new Set<AbortController>());
  useLayoutEffect(() => {
    const active = pool.current;
    return () => {
      active.forEach(controller => controller.abort());
      active.clear();
    };
  }, []);
  return useCallback(() => {
    const controller = new AbortController();
    pool.current.add(controller);
    return {
      signal: controller.signal,
      abort: () => { controller.abort(); pool.current.delete(controller); },
      done: () => { pool.current.delete(controller); },
    };
  }, []);
}

const statusOf = (error: unknown) => (error as { response?: { status?: number } })?.response?.status;
const denied = (error: unknown) => [401, 403, 404].includes(statusOf(error) ?? 0);
function readinessOf(error: unknown): StatusMessage | undefined {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  switch (detail) {
    case "d4_not_verified":
    case "d5_not_adopted":
    case "sources_unavailable":
    case "too_large":
      return `readiness.${detail}`;
  }
}
const targetKey = (target: ImpactTarget) => JSON.stringify([target.fmeaId, target.approvedVersionId]);
const optionKey = (option: ImpactOption) => JSON.stringify([option.installationId, option.deploymentId]);
const resultKey = (taskId: string, resultId: string) => `${taskId}/${resultId}`;
const PAGE_SIZE = 20;
const terminal = ["completed", "failed", "cancelled"];

function ListedText({ heading, items }: { heading: string; items: readonly string[] }) {
  if (!items.length) return null;
  return <div>
    <strong>{heading}</strong>
    <ul>{items.map((text, index) => <li key={index}>{text}</li>)}</ul>
  </div>;
}

function RecommendationView({ reportId, recommendationId, client, onReassess }: {
  reportId: string; recommendationId: string; client: PfmeaImpactClients; onReassess?: () => void;
}) {
  const { t } = useTranslation("capa", { keyPrefix: "pfmeaImpact" });
  const request = useAbortScope();
  const currentEvidence = useRef<ReturnType<typeof request>>();
  const accessDenied = useRef(false);
  const [view, setView] = useState<ImpactRecommendation | null>();
  const [evidence, setEvidence] = useState<Evidence | null>(null);

  useEffect(() => {
    const read = request();
    accessDenied.current = false;
    setView(undefined);
    setEvidence(null);
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      let permitted = false;
      try {
        const value = await client.readRecommendation(reportId, recommendationId, read.signal);
        if (!read.signal.aborted && !accessDenied.current) {
          setView(value);
          permitted = value !== null;
        }
      } catch {
        if (!read.signal.aborted) setView(null);
      } finally {
        if (permitted) timer = setTimeout(refresh, 5000);
        else if (!read.signal.aborted) {
          read.done();
          currentEvidence.current?.abort();
          setEvidence(null);
        }
      }
    };
    void refresh();
    return () => {
      clearTimeout(timer);
      read.abort();
      currentEvidence.current?.abort();
    };
  }, [client, reportId, recommendationId, request]);

  async function openEvidence(id: string) {
    if (!client.readEvidence) return;
    currentEvidence.current?.abort();
    const read = request();
    currentEvidence.current = read;
    setEvidence(null);
    try {
      const value = await client.readEvidence(reportId, recommendationId, id, read.signal);
      if (read.signal.aborted) return;
      if (!value) {
        accessDenied.current = true;
        setView(null);
      }
      else setEvidence(value);
    } catch {
      if (!read.signal.aborted) {
        accessDenied.current = true;
        setView(null);
      }
    } finally {
      read.done();
    }
  }

  if (view === undefined) return <Spin size="small" aria-label={t("loading")} />;
  if (!view) return <Alert type="warning" message={t("unavailable")} />;

  return <section aria-label={t("recommendation")}>
    <h4>{t("recommendation")}</h4>
    <Tag>{t(`conclusion.${view.conclusion}`)}</Tag>
    {view.freshness === "stale" && <Tag color="warning">{t("stale")}</Tag>}
    <p>{t("versions", { reportVersion: view.reportVersionLabel, approvedVersion: view.approvedVersionLabel })}</p>
    {view.measures.map(item => <article key={item.measureId}>
      <p><strong>{item.text}</strong></p>
      <Tag>{t(`conclusion.${item.conclusion}`)}</Tag>
      <p>{item.formalRevision === null ? t("adoption") : t("revision", { version: item.formalRevision })}</p>
      <ListedText heading={t("facts")} items={item.facts} />
      {item.inference && <p>{t("inference", { value: item.inference })}</p>}
      <p>{t("reason", { value: item.reason })}</p>
      <ListedText heading={t("adjustments")} items={item.adjustments} />
      <ListedText heading={t("gaps")} items={item.gaps} />
      {item.evidence.length > 0 && <ul aria-label={t("evidence")}>
        {item.evidence.map(reference => <li key={reference.id}>
          {client.readEvidence ? <Button type="link" onClick={() => void openEvidence(reference.id)}>
            {reference.label}
          </Button> : reference.label}
        </li>)}
      </ul>}
    </article>)}
    {evidence && <section aria-label={t("evidence")}>
      <strong>{evidence.label}</strong><p>{evidence.text}</p>
    </section>}
    {onReassess && <Button onClick={onReassess}>{t("reassess")}</Button>}
  </section>;
}

function OpenPanel({ reportId, client, recommendationId, activeTask, onStarted, requestKeys, canGenerate = true }: Props & {
  requestKeys: Map<string, string>;
}) {
  const { t } = useTranslation("capa", { keyPrefix: "pfmeaImpact" });
  const targetId = useId();
  const optionId = useId();
  const historicId = useId();
  const request = useAbortScope();
  const starting = useRef(false);
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [targets, setTargets] = useState<Awaited<ReturnType<PfmeaImpactClients["listTargets"]>>>();
  const [selection, setSelection] = useState("");
  const [pending, setPending] = useState(false);
  const [started, setStarted] = useState<ImpactTaskStatusView | null>(null);
  const [message, setMessage] = useState<StatusMessage | null>(null);
  const [options, setOptions] = useState<readonly ImpactOption[] | null>();
  const [optionIdValue, setOptionIdValue] = useState("");
  const [pastPage, setPastPage] = useState(1);
  const [results, setResults] = useState<Awaited<ReturnType<NonNullable<PfmeaImpactClients["listResults"]>>>>(null);
  const [pastChoice, setPastChoice] = useState("");
  const [predecessor, setPredecessor] = useState<string>();
  const [hiddenTask, hideTask] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const launchBusy = useRef(false);
  const cancelBusy = useRef(false);

  useEffect(() => {
    if (!canGenerate) return;
    const read = request();
    setTargets(undefined);
    setSelection("");
    void client.listTargets(reportId, { page, pageSize: PAGE_SIZE }, read.signal)
      .then(value => { if (!read.signal.aborted) setTargets(value); })
      .catch(error => {
        if (read.signal.aborted) return;
        setTargets(denied(error) ? null : { items: [], total: 0 });
        if (!denied(error)) setMessage("retry");
      }).finally(read.done);
    return read.abort;
  }, [canGenerate, client, page, reload, reportId, request]);

  const selected = targets?.items.find(item => targetKey(item) === selection);
  const chosen = options?.find(option => optionKey(option) === optionIdValue);
  const status = started && activeTask?.taskId === started.taskId ? activeTask : started;
  const taskId = status?.taskId;
  const shownResult = hiddenTask ? "" : status?.resultId ? resultKey(status.taskId, status.resultId) : "";

  useEffect(() => {
    setOptionIdValue("");
    setOptions(undefined);
    if (!selected || !client.listOptions) return;
    const read = request();
    void client.listOptions(reportId, selected, read.signal)
      .then(value => { if (!read.signal.aborted) setOptions(value); })
      .catch(() => { if (!read.signal.aborted) setOptions(null); }).finally(read.done);
    return read.abort;
  }, [client, reportId, request, selected]);

  useEffect(() => {
    if (!taskId || !client.readTask || hiddenTask || terminal.includes(status?.status ?? "")) return;
    const read = request();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const value = await client.readTask!(reportId, taskId, read.signal);
        if (read.signal.aborted) return;
        if (!value) { hideTask(true); setPastChoice(""); return; }
        setStarted(value);
        if (terminal.includes(value.status)) return;
      } catch {
        if (read.signal.aborted) return;
        hideTask(true);
        setPastChoice("");
        return;
      }
      timer = setTimeout(refresh, 1500);
    };
    void refresh();
    return () => { read.abort(); clearTimeout(timer); };
  }, [client, reportId, request, taskId, hiddenTask, status?.status]);

  useEffect(() => {
    if (!client.listResults) return;
    const read = request();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const value = await client.listResults!(reportId, { page: pastPage, pageSize: PAGE_SIZE }, read.signal);
        if (!read.signal.aborted) {
          setResults(value);
          setPastChoice(previous => value?.items.some(item => resultKey(item.taskId, item.resultId) === previous)
            ? previous : "");
          timer = setTimeout(refresh, 6000);
        }
      } catch {
        if (!read.signal.aborted) {
          setResults(null);
          setPastChoice("");
        }
      }
    };
    void refresh();
    return () => { clearTimeout(timer); read.abort(); };
  }, [client, reportId, request, pastPage, shownResult]);

  async function startAssessment() {
    if (!canGenerate || !selected || started || starting.current || (client.listOptions && !chosen)) return;
    starting.current = true;
    const read = request();
    const selectionKey = JSON.stringify([selection, chosen?.installationId, chosen?.deploymentId, predecessor]);
    let key = requestKeys.get(selectionKey);
    if (key === undefined) {
      key = crypto.randomUUID();
      requestKeys.set(selectionKey, key);
    }
    setPending(true);
    setMessage(null);
    try {
      const task = await client.start(reportId, {
        fmeaId: selected.fmeaId, approvedVersionId: selected.approvedVersionId, requestKey: key,
        ...(chosen ? { installationId: chosen.installationId, deploymentId: chosen.deploymentId } : {}),
        ...(predecessor ? { previousResultId: predecessor } : {}),
      }, read.signal);
      if (read.signal.aborted) return;
      if (task === null) {
        setTargets(null);
        setSelection("");
        return;
      }
      setStarted(task);
      setPredecessor(undefined);
      onStarted?.(task);
    } catch (error) {
      if (read.signal.aborted) return;
      if (denied(error)) {
        setTargets(null);
        setSelection("");
      } else if (statusOf(error) === 409) {
        const readiness = readinessOf(error);
        if (readiness) {
          setMessage(readiness);
        } else {
          requestKeys.delete(selectionKey);
          setTargets(undefined);
          setSelection("");
          setMessage("versionChanged");
          setReload(value => value + 1);
        }
      } else {
        setMessage("retry");
      }
    } finally {
      read.done();
      starting.current = false;
      if (!read.signal.aborted) setPending(false);
    }
  }

  async function control(action: "launch" | "cancel") {
    if (!taskId || !client[action]) return;
    const busy = action === "launch" ? launchBusy : cancelBusy;
    const mark = action === "launch" ? setLaunching : setCancelling;
    if (busy.current) return;
    busy.current = true;
    mark(true);
    setMessage(null);
    const read = request();
    try {
      const value = await client[action]!(reportId, taskId, read.signal);
      if (!read.signal.aborted) {
        if (!value) hideTask(true);
        else {
          setStarted(previous => previous?.status === "cancelled" ? previous : value);
          hideTask(false);
        }
      }
    } catch {
      if (!read.signal.aborted) setMessage("retry");
    } finally {
      read.done();
      busy.current = false;
      if (!read.signal.aborted) mark(false);
    }
  }

  const visibleRecommendation = recommendationId || pastChoice || shownResult;
  const canReassess = canGenerate && client.listOptions && !predecessor && (!status || terminal.includes(status.status));
  function reassess() {
    setPredecessor(visibleRecommendation?.split("/")[1]);
    setStarted(null);
    setPastChoice("");
    hideTask(false);
    setReload(value => value + 1);
  }
  return <section aria-label={t("title")}>
    <h3>{t("title")}</h3>
    {canGenerate && targets === undefined && <Spin size="small" aria-label={t("loading")} />}
    {canGenerate && targets === null && <Alert type="warning" message={t("unavailable")} />}
    {canGenerate && targets && targets.total === 0 && message !== "retry" && <p>{t("noTargets")}</p>}
    {canGenerate && targets && targets.total > 0 && <>
      <label htmlFor={targetId}>{t("target")}</label>{" "}
      <select id={targetId} value={selection} disabled={pending || started !== null}
        onChange={event => { setSelection(event.target.value); setMessage(null); }}>
        <option value="">{t("chooseTarget")}</option>
        {targets.items.map(item => <option key={targetKey(item)} value={targetKey(item)}>
          {item.documentNo} · {item.title} · {item.approvedVersionLabel}
        </option>)}
      </select>
      <div>
        {page > 1 && <Button size="small" disabled={pending || started !== null}
          onClick={() => { setTargets(undefined); setSelection(""); setPage(page - 1); }}>{t("previousPage")}</Button>}
        {page * PAGE_SIZE < targets.total && <Button size="small" disabled={pending || started !== null}
          onClick={() => { setTargets(undefined); setSelection(""); setPage(page + 1); }}>{t("nextPage")}</Button>}
      </div>
      {selected && <>
        <p>{t("approvedBaseline", { version: selected.approvedVersionLabel })}</p>
        {selected.hasUnapprovedRevision && <p>{t("unapprovedRevision")}</p>}
        {client.listOptions && <>
          <label htmlFor={optionId}>{t("model")}</label>{" "}
          <select id={optionId} value={optionIdValue} disabled={pending || started !== null || !options?.length}
            onChange={event => setOptionIdValue(event.target.value)}>
            <option value="">{t("chooseModel")}</option>
            {options?.map(option => <option key={optionKey(option)} value={optionKey(option)}>
              {option.name} · {option.version} · {t(`kind.${option.kind}`)}
            </option>)}
          </select>
          {options === undefined && <Spin size="small" aria-label={t("loading")} />}
          {options === null && <p>{t("noOptions")}</p>}
          {options?.length === 0 && <p>{t("noOptions")}</p>}
        </>}
      </>}
      <Button type="primary" loading={pending}
        disabled={!selected || pending || started !== null || (!!client.listOptions && !chosen)}
        onClick={() => void startAssessment()}>{t("start")}</Button>
    </>}
    {message && <Alert type="warning" message={t(message)} />}
    {message === "retry" && !targets?.total && <Button onClick={() => {
      setMessage(null);
      setReload(value => value + 1);
    }}>{t("reload")}</Button>}
    {status && !hiddenTask && <p role="status">{t(`status.${status.status}`)}</p>}
    {hiddenTask && <Alert type="warning" message={t("unavailable")} />}
    {client.launch && status && !hiddenTask && ["ready", "blocked_capability"].includes(status.status) &&
      <Button loading={launching} onClick={() => void control("launch")}>{t("launch")}</Button>}
    {client.cancel && status && !terminal.includes(status.status) &&
      <Button loading={cancelling} onClick={() => void control("cancel")}>{t("cancel")}</Button>}
    {results && (results.items.length > 0 || pastPage > 1) && <section aria-label={t("history")}>
      <label htmlFor={historicId}>{t("history")}</label>{" "}
      <select id={historicId} value={pastChoice} onChange={event => setPastChoice(event.target.value)}>
        <option value="">{t("chooseResult")}</option>
        {results.items.map(item => <option key={item.resultId} value={resultKey(item.taskId, item.resultId)}>
          {item.approvedVersionLabel} · {new Date(item.createdAt).toLocaleString()}
        </option>)}
      </select>
      <Button size="small" disabled={pastPage <= 1} onClick={() => {
        setPastChoice(""); setPastPage(pastPage - 1);
      }}>{t("previousPage")}</Button>
      <Button size="small" disabled={!results.hasMore} onClick={() => {
        setPastChoice(""); setPastPage(pastPage + 1);
      }}>{t("nextPage")}</Button>
    </section>}
    {visibleRecommendation && <RecommendationView key={visibleRecommendation} reportId={reportId}
      recommendationId={visibleRecommendation} client={client} onReassess={canReassess ? reassess : undefined} />}
  </section>;
}

function ScopedPanel(props: Props) {
  // Preserve ambiguous start retries when the same panel is closed and
  // reopened. Only the idempotency keys live beyond an individual opening.
  const requestKeys = useRef(new Map<string, string>());
  return props.open === false ? null : <OpenPanel {...props} requestKeys={props.requestKeyStore ?? requestKeys.current} />;
}

export default function PfmeaImpactPanel(props: Props) {
  if (!props.reportId || !props.scopeKey) return null;
  const session = JSON.stringify([props.scopeKey, props.reportId, props.authorityEpoch ?? 0]);
  return <ScopedPanel key={session} {...props} />;
}
