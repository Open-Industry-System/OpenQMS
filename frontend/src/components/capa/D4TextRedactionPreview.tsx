import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Input, Modal, Space, Tag, Typography } from 'antd';
import { createD4TextPreview, getD4PreviewAvailability, getD4PreviewVersion } from '../../api/capaD4TextPreview';
import { useAuthStore } from '../../store/authStore';
import { useProductLineStore } from '../../store/productLineStore';
import type { D4TextPreview } from '../../types/capaD4TextPreview';

const labels = { d4_root_cause: 'D4 根因正文', root_cause_text: '验证根因文本', result: '验证结果文本' };
export default function D4TextRedactionPreview({ reportId }: { reportId: string }) {
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
      if (alive()) withdraw('候选已到期，请重新生成。');
    }, Math.min(30000, Math.max(0, Date.parse(visible.expires_at) - Date.now())));
    const poll = window.setInterval(() => {
      if (!alive() || checking) return;
      checking = true;
      const controller = new AbortController();
      versionController.current = controller;
      void getD4PreviewVersion(reportId, controller.signal).then(value => {
        if (alive() && (value.source_version !== visible.source_version || value.rule_version !== visible.rule_version)) {
          withdraw('来源已变化，请重新生成候选。', true);
        }
      }).catch(() => {
        if (alive()) withdraw('无法确认当前访问或来源，候选已撤回。', true);
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
      if (Date.parse(value.expires_at) <= Date.now()) { withdraw('候选已到期，请重新生成。'); return; }
      setCandidate({ session: captured, value }); setNotice('');
    } catch (error) {
      if (!controller.signal.aborted && currentSession.current === captured && epoch.current === capturedEpoch) {
        const status = (error as { response?: { status?: number } })?.response?.status;
        withdraw('无法生成候选，请检查替换词及当前对象访问权限。', [401, 403, 404].includes(status ?? 0));
      }
    } finally {
      if (!controller.signal.aborted && currentSession.current === captured && epoch.current === capturedEpoch) setPending(false);
    }
  }
  if (!available) return null;
  return <>
    <Button onClick={() => setOpen(true)}>正文脱敏候选预览</Button>
    {open && <Modal title="D4 正文脱敏候选预览" open onCancel={close} destroyOnClose transitionName="" maskTransitionName=""
      width={760} styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}
      footer={<Button onClick={close}>关闭预览</Button>}>
      <Alert type="warning" showIcon message="受限脱敏候选，可能仍含敏感内容"
        description="规则替换不代表完全脱敏或已批准降敏。仅供内部检查，不向插件或模型交付，不改写业务原文。" />
      <label style={{ display: 'block', marginTop: 16 }}>
        显式替换词
        <Input.TextArea aria-label="显式替换词" value={terms} rows={3} maxLength={8192}
          placeholder="每行一个需遮盖的词，最多50项；按字面匹配，不接受正则。"
          onChange={event => { withdraw(); setTerms(event.target.value); }} />
      </label>
      <Button aria-label="生成受限候选" style={{ marginTop: 12 }} onClick={() => void generate()} loading={pending} disabled={pending}>生成受限候选</Button>
      {notice && <p role="status" aria-live="polite">{notice}</p>}
      {visible && <section aria-label="受限正文预览" style={{ marginTop: 16 }}>
        <Space wrap><Tag color="warning">restricted</Tag><Tag>未批准降敏</Tag><Tag>外发关闭</Tag></Space>
        <Typography.Paragraph style={{ fontFamily: 'monospace', overflowWrap: 'anywhere', marginTop: 8 }}>
          源版本 {visible.source_version}<br />规则 {visible.rule_version}<br />有效至 {visible.expires_at}
        </Typography.Paragraph>
        {visible.fields.map(value => <section key={`${value.verification_id}:${value.field}`}
          style={{ borderTop: '1px solid #d9d9d9', paddingBlock: 12 }}>
          <Typography.Title level={5}>{labels[value.field]}</Typography.Title>
          {value.verification_id && <p style={{ overflowWrap: 'anywhere' }}>验证记录 {value.verification_id}</p>}
          <Tag>{value.source_status === 'unverified' ? '语义来源未确认' : '引用已校验（非降敏批准）'}</Tag>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'inherit', marginBlock: 10 }}>
            {value.redacted_text ?? '暂无正文'}
          </pre>
          <p>规则命中 {Object.entries(value.match_counts).map(([kind, count]) => `${kind}: ${count}`).join(' · ') || '无'}</p>
          {value.source_ref && <p style={{ overflowWrap: 'anywhere' }}>FMEA 来源 {value.source_ref.object_id} · 节点 {value.source_ref.node_id} · 版本 {value.source_ref.version}</p>}
        </section>)}
      </section>}
    </Modal>}
  </>;
}
