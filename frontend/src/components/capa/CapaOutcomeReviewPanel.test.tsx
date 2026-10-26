import { render, screen, fireEvent, configure, act } from '@testing-library/react';
import { App } from 'antd';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, afterAll, it, expect, vi } from 'vitest';
import * as capaApi from '../../api/capa';
import CapaOutcomeReviewPanel from './CapaOutcomeReviewPanel';
import i18n from '../../i18n';
import type { CapaOutcomeReview } from '../../types/capaOutcomeReview';

vi.mock('../../api/capa', async () => ({
  ...await vi.importActual<typeof import('../../api/capa')>('../../api/capa'),
  getCapaOutcomeReview: vi.fn(),
}));
configure({ testIdAttribute: 'data-e2e' });
afterAll(() => { configure({ testIdAttribute: 'data-testid' }); void i18n.changeLanguage('en-US'); });
const id = '00000000-0000-4000-8000-000000000001';
const source = '00000000-0000-4000-8000-000000000004';
const fixture: CapaOutcomeReview = {
  report_id: id, status: 'D8_APPROVAL_PENDING', contract: 'capa.outcome-review.v1',
  review_round_id: '00000000-0000-4000-8000-000000000002', revision: '1'.repeat(64), binding_status: 'pending',
  core: { d4_root_cause: '扭矩不足', d5_correction: '更换扭矩控制工具', d6_verification: '实施后复测合格', d7_prevention: '更新点检要求' },
  verifications: [{
    verification_id: '00000000-0000-4000-8000-000000000003', capa_id: id,
    root_cause_text: '扭矩不足', method: 'observation', result: '复测合格',
    is_verified: true, conclusion: 'passed', evidence_attachments: [{ name: '<img src=x onerror=alert(1)>', url: 'https://untrusted.invalid/private' }],
    source_ref: { fmea_id: source, cause_node_id: 'cause-1' },
    verified_by: id, verified_at: '2026-10-23T00:00:00Z', created_at: '2026-10-23T00:00:00Z',
  }],
  d7_actions: [{ action_id: id, capa_id: id, action: 'confirmed', status: 'pending', fmea_id: source,
    failure_mode_node_id: 'fm-1', failure_cause_node_id: 'cause-1', match_source: 'linked',
    prevention_control_node_id: 'pc-1', prevention_control_name_before: '原点检', prevention_control_name_after: '新版点检',
    reason: '现场确认', acted_by: id, acted_at: '2026-10-23T00:00:00Z' }],
  documents: [{ module: 'fmea', object_id: source, version_id: id, sha256: 'a'.repeat(64) },
    { module: 'planning', object_id: id, version_id: source, sha256: 'b'.repeat(64) }], decision: null,
  supplement: { text: '补充说明', review_scope: 'unreviewed_supplement', updated_by: null, updated_at: null },
};
const deferred = <T,>() => { let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((r, j) => { resolve = r; reject = j; }); return { promise, resolve, reject }; };
const changed = vi.fn();
const view = (identity = 'A', status = 'D8_APPROVAL_PENDING') => <App><BrowserRouter><CapaOutcomeReviewPanel
  reportId={id} status={status} canApprove credentialIdentity={identity} onReviewChange={changed}
/></BrowserRouter></App>;
beforeEach(async () => { await i18n.changeLanguage('zh-CN'); vi.clearAllMocks(); vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue(structuredClone(fixture)); });

it('shows actual complete DTO materials, source versions and escaped evidence; supplement is not reviewed core', async () => {
  render(view());
  expect(await screen.findByText('实施后复测合格')).toBeInTheDocument();
  expect(screen.getByText('更换扭矩控制工具')).toBeInTheDocument();
  expect(screen.getByText('结案后补充，未纳入本次审核')).toBeInTheDocument();
  expect(screen.getByTestId('capa-outcome-core')).not.toHaveTextContent('补充说明');
  expect(screen.getByTestId('capa-outcome-core')).not.toHaveTextContent('有效');
  expect(screen.getByText('新版点检')).toBeInTheDocument();
  expect(screen.getByTestId('capa-outcome-d7')).toHaveTextContent('待确认');
  expect(screen.getByTestId('capa-outcome-d7')).not.toHaveTextContent('已验证');
  expect(screen.getByText('a'.repeat(64))).toBeInTheDocument();
  expect(screen.getByText('b'.repeat(64))).toBeInTheDocument();
  expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
  expect(document.querySelector('img,iframe,object,embed')).toBeNull();
  expect(document.querySelector('a[href^="https:"]')).toBeNull();
  expect(changed).toHaveBeenLastCalledWith(fixture);
});

it.each([401, 403, 404, 409])('withdraws a prior token before reload and on %s, without partial material fallback', async status => {
  render(view()); await screen.findByText('实施后复测合格');
  const read = deferred<CapaOutcomeReview>(); vi.mocked(capaApi.getCapaOutcomeReview).mockReturnValueOnce(read.promise);
  fireEvent.click(screen.getByRole('button', { name: '重新加载审核材料' }));
  expect(changed).toHaveBeenLastCalledWith(null);
  expect(screen.queryByText('实施后复测合格')).not.toBeInTheDocument();
  await act(async () => read.reject({ response: { status } }));
  expect(changed).toHaveBeenLastCalledWith(null);
  expect(screen.getByRole('alert')).toBeInTheDocument();
});

it.each(['success', 'denial'])('same-document identity change aborts old requests and ignores late %s', async result => {
  const old = deferred<CapaOutcomeReview>(); vi.mocked(capaApi.getCapaOutcomeReview).mockReturnValueOnce(old.promise);
  const { rerender, unmount } = render(view('A'));
  const firstSignal = vi.mocked(capaApi.getCapaOutcomeReview).mock.calls[0][1]!;
  rerender(view('B')); await screen.findByText('实施后复测合格');
  expect(firstSignal.aborted).toBe(true);
  const calls = vi.mocked(capaApi.getCapaOutcomeReview).mock.calls;
  const lastSignal = calls[calls.length - 1][1]!;
  const publishedCount = changed.mock.calls.length;
  await act(async () => result === 'success' ? old.resolve({ ...fixture, revision: 'c'.repeat(64), core: { ...fixture.core, d5_correction: 'OLD PRIVATE' } }) : old.reject({ response: { status: 403 } }));
  expect(changed).toHaveBeenCalledTimes(publishedCount);
  expect(screen.queryByText('OLD PRIVATE')).not.toBeInTheDocument();
  expect(screen.getByText('实施后复测合格')).toBeInTheDocument();
  unmount(); expect(lastSignal).toBeInstanceOf(AbortSignal);
});

it.each(['legacy_unversioned', 'unverifiable', 'verified'] as const)('labels %s honestly without offering pending expectations', async binding_status => {
  vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({ ...fixture, status: 'D8_CLOSURE', binding_status, review_round_id: null,
    decision: binding_status === 'verified' ? { action: 'approved', actor_id: id, operated_at: '2026-10-23T00:00:00Z', audit_id: source } : null });
  render(view('A', 'D8_CLOSURE')); await screen.findByText('实施后复测合格');
  expect(screen.getByTestId('capa-outcome-binding')).toHaveTextContent(binding_status === 'legacy_unversioned' ? '历史记录，未绑定审核版本' : binding_status === 'unverifiable' ? '无法验证审核绑定' : '已核对审核版本');
  expect(screen.queryByRole('button', { name: /审批|驳回/ })).not.toBeInTheDocument();
});

it.each(['missing documents', 'wrong report', 'missing core', 'wrong status', 'missing necessary source', 'unknown source shape'])('fails closed for partial or mismatched DTO: %s', async kind => {
  const value: any = structuredClone(fixture);
  if (kind === 'missing documents') delete value.documents;
  if (kind === 'wrong report') value.report_id = source;
  if (kind === 'missing core') delete value.core.d6_verification;
  if (kind === 'wrong status') value.status = 'ARCHIVED';
  if (kind === 'missing necessary source') value.documents = [];
  if (kind === 'unknown source shape') value.verifications[0].source_ref = { object_id: source, node_id: 'cause-1', version: 'v1', module: 'fmea' };
  vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue(value);
  render(view()); await screen.findByRole('alert');
  expect(changed).toHaveBeenLastCalledWith(null);
  expect(screen.queryByText('实施后复测合格')).not.toBeInTheDocument();
});


it('keeps ordinary formal materials visible after 30 seconds without browser persistence', async () => {
  const write = vi.spyOn(localStorage, 'setItem');
  render(view()); await screen.findByText('实施后复测合格');
  expect(write).not.toHaveBeenCalled();
  const writes = write.mock.calls.length;
  vi.useFakeTimers();
  try {
    await act(async () => { vi.advanceTimersByTime(31000); });
    expect(screen.getByText('实施后复测合格')).toBeInTheDocument();
    expect(changed).toHaveBeenLastCalledWith(fixture);
    expect(write.mock.calls.length).toBe(writes);
  } finally { vi.useRealTimers(); write.mockRestore(); }
});

it('aborts an in-flight read on close and ignores its later denial', async () => {
  const read = deferred<CapaOutcomeReview>(); vi.mocked(capaApi.getCapaOutcomeReview).mockReturnValueOnce(read.promise);
  const { unmount } = render(view());
  const signal = vi.mocked(capaApi.getCapaOutcomeReview).mock.calls[0][1]!;
  unmount(); expect(signal.aborted).toBe(true);
  const count = changed.mock.calls.length;
  await act(async () => read.reject({ response: { status: 403 } }));
  expect(changed).toHaveBeenCalledTimes(count);
});
