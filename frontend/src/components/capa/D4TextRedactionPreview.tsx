import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Input, Modal, Space, Tag, Typography } from 'antd';
import { createD4TextPreview, getD4PreviewAvailability, getD4PreviewVersion } from '../../api/capaD4TextPreview';
import { useAuthStore } from '../../store/authStore';
import { useProductLineStore } from '../../store/productLineStore';
import type { D4TextPreview } from '../../types/capaD4TextPreview';
import { tr, useTr } from "../../i18n/tr";

const labels = () => ({ d4_root_cause: tr("D4-Grundursachentext", "D4 root cause text"), root_cause_text: tr("Text der verifizierten Grundursache", "Verification root cause text"), result: tr("Text des Verifizierungsergebnisses", "Verification result text") });
export default function D4TextRedactionPreview({ reportId }: { reportId: string }) {
  useTr();
  const userId = useAuthStore(state => state.user?.user_id);
  const token = useAuthStore(state => state.token);
  const factory = useAuthStore(state => state.currentFactoryId);
  const line = useProductLineStore(state => state.selected);
  const session = JSON.stringify([reportId, userId, token, factory, line, localStorage.getItem('tenant_slug')]);
  const currentSession = useRef(session);
  currentSession.current = session;
  const epoch = useRef(0);
  const generateController = useRef<AbortController | null>(null);
  const versionController = useRef<AbortController | null>(null);
  const [available, setAvailable] = useState(false);
  const [open, setOpen] = useState(false);
  const [terms, setTerms] = useState('');
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState('');
  const [candidate, setCandidate] = useState<{ session: string; value: D4TextPreview } | null>(null);
  const withdraw = useCallback((message = '', clearTerms = false) => {
    if (clearTerms) setTerms('');
    epoch.current += 1;
    generateController.current?.abort();
    versionController.current?.abort();
    setCandidate(null); setPending(false); setNotice(message);
  }, []);
  const close = useCallback(() => {
    withdraw(); setTerms(''); setOpen(false);
  }, [withdraw]);
  useEffect(() => {
    close(); setAvailable(false);
    if (!userId || !token) return;
    const controller = new AbortController();
    const captured = session;
    void getD4PreviewAvailability(reportId, controller.signal).then(() => {
      if (!controller.signal.aborted && currentSession.current === captured) setAvailable(true);
    }).catch(() => {
      if (!controller.signal.aborted && currentSession.current === captured) setAvailable(false);
    });
    return () => { controller.abort(); generateController.current?.abort(); versionController.current?.abort(); };
  }, [session, reportId, userId, token, close]);
  useEffect(() => {
    const hidden = () => { if (document.hidden) close(); };
    document.addEventListener('visibilitychange', hidden);
    return () => document.removeEventListener('visibilitychange', hidden);
  }, [close]);
  const visible = open && !document.hidden && candidate?.session === session ? candidate.value : null;
  useEffect(() => {
    if (!visible) return;
    const captured = session, capturedEpoch = epoch.current;
    let active = true, checking = false;
    const alive = () => active && currentSession.current === captured && epoch.current === capturedEpoch && !document.hidden;
    const expiry = window.setTimeout(() => {
      if (alive()) withdraw(tr("Kandidat ist abgelaufen, bitte neu erzeugen.", "Candidate expired, please regenerate."));
    }, Math.min(30000, Math.max(0, Date.parse(visible.expires_at) - Date.now())));
    const poll = window.setInterval(() => {
      if (!alive() || checking) return;
      checking = true;
      const controller = new AbortController();
      versionController.current = controller;
      void getD4PreviewVersion(reportId, controller.signal).then(value => {
        if (alive() && (value.source_version !== visible.source_version || value.rule_version !== visible.rule_version)) {
          withdraw(tr("Quelle hat sich geändert, bitte Kandidaten neu erzeugen.", "Source changed, please regenerate the candidate."), true);
        }
      }).catch(() => {
        if (alive()) withdraw(tr("Zugriff oder Quelle konnte nicht bestätigt werden, Kandidat wurde zurückgezogen.", "Could not confirm access or source; candidate withdrawn."), true);
      }).finally(() => { checking = false; });
    }, 2000);
    return () => {
      active = false; window.clearTimeout(expiry); window.clearInterval(poll); versionController.current?.abort();
    };
  }, [visible, session, reportId, withdraw]);
  async function generate() {
    withdraw();
    const captured = session, capturedEpoch = epoch.current;
    const controller = new AbortController();
    generateController.current = controller;
    setPending(true);
    try {
      const replacement_terms = terms.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
      const value = await createD4TextPreview(reportId, { replacement_terms }, controller.signal);
      if (controller.signal.aborted || currentSession.current !== captured || epoch.current !== capturedEpoch || document.hidden) return;
      if (Date.parse(value.expires_at) <= Date.now()) { withdraw(tr("Kandidat ist abgelaufen, bitte neu erzeugen.", "Candidate expired, please regenerate.")); return; }
      setCandidate({ session: captured, value }); setNotice('');
    } catch (error) {
      if (!controller.signal.aborted && currentSession.current === captured && epoch.current === capturedEpoch) {
        const status = (error as { response?: { status?: number } })?.response?.status;
        withdraw(tr("Kandidat kann nicht erzeugt werden, bitte Ersetzungsbegriffe und Zugriffsrechte prüfen.", "Cannot generate candidate; check replacement terms and object access."), [401, 403, 404].includes(status ?? 0));
      }
    } finally {
      if (!controller.signal.aborted && currentSession.current === captured && epoch.current === capturedEpoch) setPending(false);
    }
  }
  if (!available) return null;
  return <>
    <Button onClick={() => setOpen(true)}>{tr("Vorschau anonymisierter Text", "Redacted text preview")}</Button>
    {open && <Modal title={tr("D4: Vorschau anonymisierter Text", "D4 redacted text preview")} open onCancel={close} destroyOnClose transitionName="" maskTransitionName=""
      width={760} styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}
      footer={<Button onClick={close}>{tr("Vorschau schließen", "Close preview")}</Button>}>
      <Alert type="warning" showIcon message={tr("Eingeschränkter anonymisierter Kandidat – kann noch sensible Inhalte enthalten", "Restricted redaction candidate – may still contain sensitive content")}
        description={tr("Regelbasierte Ersetzung bedeutet keine vollständige oder freigegebene Anonymisierung. Nur zur internen Prüfung, wird nicht an Plugins oder Modelle übergeben und ändert den Originaltext nicht.", "Rule-based replacement is not full or approved redaction. For internal review only; never delivered to plugins or models and does not modify the original text.")} />
      <label style={{ display: 'block', marginTop: 16 }}>
        {tr("Explizite Ersetzungsbegriffe", "Explicit replacement terms")}
        <Input.TextArea aria-label={tr("Explizite Ersetzungsbegriffe", "Explicit replacement terms")} value={terms} rows={3} maxLength={8192}
          placeholder={tr("Ein Begriff pro Zeile, höchstens 50; wörtlicher Abgleich, keine regulären Ausdrücke.", "One term per line, max. 50; literal match, no regular expressions.")}
          onChange={event => { withdraw(); setTerms(event.target.value); }} />
      </label>
      <Button aria-label={tr("Eingeschränkten Kandidaten erzeugen", "Generate restricted candidate")} style={{ marginTop: 12 }} onClick={() => void generate()} loading={pending} disabled={pending}>{tr("Eingeschränkten Kandidaten erzeugen", "Generate restricted candidate")}</Button>
      {notice && <p role="status" aria-live="polite">{notice}</p>}
      {visible && <section aria-label={tr("Eingeschränkte Textvorschau", "Restricted text preview")} style={{ marginTop: 16 }}>
        <Space wrap><Tag color="warning">restricted</Tag><Tag>{tr("Anonymisierung nicht freigegeben", "Redaction not approved")}</Tag><Tag>{tr("Weitergabe deaktiviert", "Export disabled")}</Tag></Space>
        <Typography.Paragraph style={{ fontFamily: 'monospace', overflowWrap: 'anywhere', marginTop: 8 }}>
          {tr("Quellversion", "Source version")} {visible.source_version}<br />{tr("Regel", "Rule")} {visible.rule_version}<br />{tr("Gültig bis", "Valid until")} {visible.expires_at}
        </Typography.Paragraph>
        {visible.fields.map(value => <section key={`${value.verification_id}:${value.field}`}
          style={{ borderTop: '1px solid #d9d9d9', paddingBlock: 12 }}>
          <Typography.Title level={5}>{labels()[value.field]}</Typography.Title>
          {value.verification_id && <p style={{ overflowWrap: 'anywhere' }}>{tr("Verifizierung", "Verification")} {value.verification_id}</p>}
          <Tag>{value.source_status === 'unverified' ? tr("Semantische Quelle nicht bestätigt", "Semantic source unconfirmed") : tr("Verweis geprüft (keine Anonymisierungsfreigabe)", "Reference verified (not a redaction approval)")}</Tag>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'inherit', marginBlock: 10 }}>
            {value.redacted_text ?? tr("Kein Text vorhanden", "No text")}
          </pre>
          <p>{tr("Regeltreffer", "Rule matches")} {Object.entries(value.match_counts).map(([kind, count]) => `${kind}: ${count}`).join(' · ') || tr("keine", "none")}</p>
          {value.source_ref && <p style={{ overflowWrap: 'anywhere' }}>{tr("FMEA-Quelle", "FMEA source")} {value.source_ref.object_id} · {tr("Knoten", "Node")} {value.source_ref.node_id} · {tr("Version", "Version")} {value.source_ref.version}</p>}
        </section>)}
      </section>}
    </Modal>}
  </>;
}
