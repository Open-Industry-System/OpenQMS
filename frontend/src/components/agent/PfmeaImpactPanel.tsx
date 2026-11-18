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
type StatusMessage = "unavailable" | "retry" | "versionChanged";

export interface PfmeaImpactClients {
  listTargets: (
    reportId: string, options: { page: number; pageSize: number }, signal: AbortSignal,
  ) => Promise<{ items: readonly ImpactTarget[]; total: number } | Unavailable>;
  /** A 409 response means the input changed and must be confirmed again. */
  start: (
    reportId: string,
    input: { fmeaId: string; approvedVersionId: string; requestKey: string },
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
  client: PfmeaImpactClients;
  recommendationId?: string;
  activeTask?: ImpactTaskStatusView;
  onStarted?: (task: ImpactTaskStatusView) => void;
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
const targetKey = (target: ImpactTarget) => JSON.stringify([target.fmeaId, target.approvedVersionId]);
const PAGE_SIZE = 20;

function ListedText({ heading, items }: { heading: string; items: readonly string[] }) {
  if (!items.length) return null;
  return <div>
    <strong>{heading}</strong>
    <ul>{items.map((text, index) => <li key={index}>{text}</li>)}</ul>
  </div>;
}

function RecommendationView({ reportId, recommendationId, client }: {
  reportId: string; recommendationId: string; client: PfmeaImpactClients;
}) {
  const { t } = useTranslation("capa", { keyPrefix: "pfmeaImpact" });
  const request = useAbortScope();
  const currentEvidence = useRef<ReturnType<typeof request>>();
  const [view, setView] = useState<ImpactRecommendation | null>();
  const [evidence, setEvidence] = useState<Evidence | null>(null);

  useEffect(() => {
    const read = request();
    setView(undefined);
    setEvidence(null);
    void client.readRecommendation(reportId, recommendationId, read.signal)
      .then(value => { if (!read.signal.aborted) setView(value); })
      .catch(() => { if (!read.signal.aborted) setView(null); })
      .finally(read.done);
    return () => {
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
      if (!value) setView(null);
      else setEvidence(value);
    } catch {
      if (!read.signal.aborted) setView(null);
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
  </section>;
}

function OpenPanel({ reportId, client, recommendationId, activeTask, onStarted, requestKeys }: Props & {
  requestKeys: Map<string, string>;
}) {
  const { t } = useTranslation("capa", { keyPrefix: "pfmeaImpact" });
  const targetId = useId();
  const request = useAbortScope();
  const starting = useRef(false);
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [targets, setTargets] = useState<Awaited<ReturnType<PfmeaImpactClients["listTargets"]>>>();
  const [selection, setSelection] = useState("");
  const [pending, setPending] = useState(false);
  const [started, setStarted] = useState<ImpactTaskStatusView | null>(null);
  const [message, setMessage] = useState<StatusMessage | null>(null);

  useEffect(() => {
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
  }, [client, page, reload, reportId, request]);

  const selected = targets?.items.find(item => targetKey(item) === selection);
  const status = started && activeTask?.taskId === started.taskId ? activeTask : started;

  async function startAssessment() {
    if (!selected || started || starting.current) return;
    starting.current = true;
    const read = request();
    let key = requestKeys.get(selection);
    if (key === undefined) {
      key = crypto.randomUUID();
      requestKeys.set(selection, key);
    }
    setPending(true);
    setMessage(null);
    try {
      const task = await client.start(reportId, {
        fmeaId: selected.fmeaId, approvedVersionId: selected.approvedVersionId, requestKey: key,
      }, read.signal);
      if (read.signal.aborted) return;
      if (task === null) {
        setTargets(null);
        setSelection("");
        return;
      }
      setStarted(task);
      onStarted?.(task);
    } catch (error) {
      if (read.signal.aborted) return;
      if (denied(error)) {
        setTargets(null);
        setSelection("");
      } else if (statusOf(error) === 409) {
        requestKeys.delete(selection);
        setTargets(undefined);
        setSelection("");
        setMessage("versionChanged");
        setReload(value => value + 1);
      } else {
        setMessage("retry");
      }
    } finally {
      read.done();
      starting.current = false;
      if (!read.signal.aborted) setPending(false);
    }
  }

  return <section aria-label={t("title")}>
    <h3>{t("title")}</h3>
    {targets === undefined && <Spin size="small" aria-label={t("loading")} />}
    {targets === null && <Alert type="warning" message={t("unavailable")} />}
    {targets && targets.total === 0 && message !== "retry" && <p>{t("noTargets")}</p>}
    {targets && targets.total > 0 && <>
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
      </>}
      <Button type="primary" loading={pending} disabled={!selected || pending || started !== null}
        onClick={() => void startAssessment()}>{t("start")}</Button>
    </>}
    {message && <Alert type="warning" message={t(message)} />}
    {message === "retry" && !targets?.total && <Button onClick={() => {
      setMessage(null);
      setReload(value => value + 1);
    }}>{t("reload")}</Button>}
    {status && <p role="status">{t(`status.${status.status}`)}</p>}
    {recommendationId && <RecommendationView key={recommendationId} reportId={reportId}
      recommendationId={recommendationId} client={client} />}
  </section>;
}

function ScopedPanel(props: Props) {
  // Preserve ambiguous start retries when the same panel is closed and
  // reopened. Only the idempotency keys live beyond an individual opening.
  const requestKeys = useRef(new Map<string, string>());
  return props.open === false ? null : <OpenPanel {...props} requestKeys={requestKeys.current} />;
}

export default function PfmeaImpactPanel(props: Props) {
  if (!props.reportId || !props.scopeKey) return null;
  const session = JSON.stringify([props.scopeKey, props.reportId, props.authorityEpoch ?? 0]);
  return <ScopedPanel key={session} {...props} />;
}
