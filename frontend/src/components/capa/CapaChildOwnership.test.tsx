import { act, configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterAll, beforeEach, expect, it, vi } from 'vitest';
import { App, message } from 'antd';
import { MemoryRouter } from 'react-router-dom';
import D4RecPanel from './D4RecPanel';
import D5RecPanel from './D5RecPanel';
import D4VerificationCard from './D4VerificationCard';
import D7RecPanel from './D7RecPanel';
import DocGatePanel from './DocGatePanel';
import D3ContainmentPanel from './D3ContainmentPanel';
import * as api from '../../api/capa';
import * as fmea from '../../api/fmea';
import { useAuthStore } from '../../store/authStore';

vi.mock('../../api/capa', async () => ({ ...await vi.importActual<typeof import('../../api/capa')>('../../api/capa'),
  getD4Recommendations: vi.fn(), getD5Recommendations: vi.fn(), adoptRecommendation: vi.fn(),
  listVerifications: vi.fn(), createVerification: vi.fn(), updateVerification: vi.fn(),
  getD7Recommendations: vi.fn(), listD7Actions: vi.fn(), recordD7Action: vi.fn(), autoFillD7: vi.fn(),
  getDocGateImpact: vi.fn(), getDocGateDecision: vi.fn(), getDocGateAudit: vi.fn(),
  getD3Runs: vi.fn(), getD3Adoptions: vi.fn(), importD3Containment: vi.fn(),
}));
vi.mock('../../api/fmea', () => ({ getFMEA: vi.fn() }));
configure({ testIdAttribute: 'data-e2e' });
afterAll(() => { configure({ testIdAttribute: 'data-testid' }); vi.restoreAllMocks(); });
const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() };
const deferred = <T,>() => { let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
function identity(name: string) {
  localStorage.setItem('access_token', name); localStorage.setItem('refresh_token', `${name}-refresh`);
  useAuthStore.setState({ token: name, user: { user_id: name, permissions: { capa: 3 } } as any });
}
const view = (node: React.ReactNode) => render(<App><MemoryRouter>{node}</MemoryRouter></App>);
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear(); identity('A');
  vi.spyOn(App, 'useApp').mockReturnValue({ message: notify } as any);
  vi.spyOn(message, 'error').mockImplementation(notify.error);
  vi.spyOn(message, 'success').mockImplementation(notify.success);
  vi.mocked(api.getD4Recommendations).mockResolvedValue({ items: [{ failure_cause_name: 'Cause A', failure_cause_node_id: 'c1', match_source: 'rule' }], stages: [] } as any);
  vi.mocked(api.getD5Recommendations).mockResolvedValue({ existing_controls: [{ control_node_id: 'pc1', control_name: 'Control A', control_type: 'prevention', match_source: 'rule' }], general_suggestions: [{ content: 'Suggestion A', category: 'prevention', match_source: 'rule' }], stages: [] } as any);
  vi.mocked(api.listVerifications).mockResolvedValue([]);
  vi.mocked(fmea.getFMEA).mockResolvedValue({ graph_data: { nodes: [] } } as any);
  vi.mocked(api.getD7Recommendations).mockResolvedValue({ recommendations: [{ fmea_id: 'f1', failure_mode_node_id: 'm1', failure_cause_node_id: 'c1', failure_mode_name: 'Mode A', failure_cause_name: 'Cause A', match_source: 'linked' }] } as any);
  vi.mocked(api.listD7Actions).mockResolvedValue([]);
});

it.each(['d4', 'control', 'suggestion'])('%s cancels the entire prerequisite/adopt continuation on credential change', async kind => {
  const before = deferred<void>(), onAdopted = vi.fn();
  view(kind === 'd4' ? <D4RecPanel capaId="report-A" beforeAdopt={() => before.promise} onAdopted={onAdopted} />
    : <D5RecPanel capaId="report-A" beforeAdopt={() => before.promise} onAdopted={onAdopted} />);
  const button = await screen.findByTestId(kind === 'd4' ? 'd4-adopt' : `d5-adopt-${kind}`);
  fireEvent.click(button);
  await act(async () => { identity('B'); });
  await act(async () => before.resolve());
  expect(api.adoptRecommendation).not.toHaveBeenCalled();
  expect(onAdopted).not.toHaveBeenCalled(); expect(notify.success).not.toHaveBeenCalled(); expect(notify.error).not.toHaveBeenCalled();
});

it.each(['success', 'denial'])('a pending D4 adoption late %s cannot toast or reload for B', async result => {
  const post = deferred<any>(), onAdopted = vi.fn(); vi.mocked(api.adoptRecommendation).mockReturnValueOnce(post.promise);
  view(<D4RecPanel capaId="report-A" onAdopted={onAdopted} />);
  fireEvent.click(await screen.findByTestId('d4-adopt'));
  await waitFor(() => expect(api.adoptRecommendation).toHaveBeenCalled());
  const signal = vi.mocked(api.adoptRecommendation).mock.calls[0][2];
  await act(async () => { identity('B'); });
  expect(signal?.aborted).toBe(true);
  await act(async () => result === 'success' ? post.resolve({}) : post.reject({ response: { status: 403 } }));
  expect(onAdopted).not.toHaveBeenCalled(); expect(notify.success).not.toHaveBeenCalled(); expect(notify.error).not.toHaveBeenCalled();
});

it.each(['success', 'denial'])('a pending verification create late %s cannot toast/reset/reload for B', async result => {
  const post = deferred<any>(); vi.mocked(api.createVerification).mockReturnValueOnce(post.promise);
  view(<D4VerificationCard capaId="report-A" canEdit currentRootCause="Cause A" fmeaRefId={null} />);
  await waitFor(() => expect(api.listVerifications).toHaveBeenCalled());
  fireEvent.click(screen.getByTestId('d4-verification-new'));
  fireEvent.click(screen.getByTestId('verify-save-draft'));
  await waitFor(() => expect(api.createVerification).toHaveBeenCalled());
  const signal = vi.mocked(api.createVerification).mock.calls[0][2];
  await act(async () => { identity('B'); });
  expect(signal?.aborted).toBe(true);
  const reads = vi.mocked(api.listVerifications).mock.calls.length;
  await act(async () => result === 'success' ? post.resolve({}) : post.reject({ response: { status: 403 } }));
  expect(api.listVerifications).toHaveBeenCalledTimes(reads);
  expect(notify.success).not.toHaveBeenCalled(); expect(notify.error).not.toHaveBeenCalled();
});

it('aborts both verification and source reads on close and ignores late denial', async () => {
  const records = deferred<any>(), source = deferred<any>();
  vi.mocked(api.listVerifications).mockReturnValueOnce(records.promise); vi.mocked(fmea.getFMEA).mockReturnValueOnce(source.promise);
  const rendered = view(<D4VerificationCard capaId="report-A" canEdit currentRootCause="Cause A" fmeaRefId="f1" />);
  const signals = [vi.mocked(api.listVerifications).mock.calls[0][1], vi.mocked(fmea.getFMEA).mock.calls[0][1]];
  rendered.unmount(); signals.forEach(signal => expect(signal?.aborted).toBe(true));
  await act(async () => { records.reject({ response: { status: 403 } }); source.reject({ response: { status: 403 } }); });
  expect(notify.error).not.toHaveBeenCalled();
});

it('D7 confirmation cannot start reload/recommendation requests after an identity switch', async () => {
  const post = deferred<any>(); vi.mocked(api.recordD7Action).mockReturnValueOnce(post.promise);
  view(<D7RecPanel capaId="report-A" d5Correction="Implemented" canAdopt canAutoFill onConfirmationChange={vi.fn()} />);
  fireEvent.click(await screen.findByTestId('d7-confirm'));
  await waitFor(() => expect(api.recordD7Action).toHaveBeenCalled());
  await act(async () => { identity('B'); });
  const actions = vi.mocked(api.listD7Actions).mock.calls.length, recs = vi.mocked(api.getD7Recommendations).mock.calls.length;
  await act(async () => post.resolve({}));
  expect(api.listD7Actions).toHaveBeenCalledTimes(actions); expect(api.getD7Recommendations).toHaveBeenCalledTimes(recs);
});

it('DocGate load cannot start subsequent reads under B when an old first read finishes', async () => {
  const first = deferred<any>(); vi.mocked(api.getDocGateImpact).mockReturnValueOnce(first.promise);
  vi.mocked(api.getDocGateDecision).mockResolvedValue({ decision: null }); vi.mocked(api.getDocGateAudit).mockResolvedValue({ audits: [], audit_run_id: null });
  view(<DocGatePanel capaId="report-A" canEdit />);
  await act(async () => { identity('B'); });
  const reads = vi.mocked(api.getDocGateDecision).mock.calls.length;
  await act(async () => first.resolve({ status: 'done' }));
  expect(api.getDocGateDecision).toHaveBeenCalledTimes(reads); expect(notify.error).not.toHaveBeenCalled();
});

it('D3 import cannot toast or start a new read under B after the write finishes', async () => {
  const post = deferred<any>(); vi.mocked(api.importD3Containment).mockReturnValueOnce(post.promise);
  vi.mocked(api.getD3Runs).mockResolvedValue([]); vi.mocked(api.getD3Adoptions).mockResolvedValue([]);
  view(<D3ContainmentPanel capa={{ report_id: 'report-A', status: 'D3_INTERIM' } as any} canEdit />);
  fireEvent.click(await screen.findByRole('button', { name: /Import|导入/ }));
  await waitFor(() => expect(api.importD3Containment).toHaveBeenCalled());
  await act(async () => { identity('B'); }); const reads = vi.mocked(api.getD3Runs).mock.calls.length;
  await act(async () => post.resolve({}));
  expect(api.getD3Runs).toHaveBeenCalledTimes(reads); expect(notify.success).not.toHaveBeenCalled();
});


it.each(['conclusion', 'source'])('verification %s PATCH owns its complete write/reload lifecycle', async kind => {
  vi.mocked(api.listVerifications).mockResolvedValue([{ verification_id: 'v1', capa_id: 'report-A', root_cause_text: 'Cause A', conclusion: 'pending', is_verified: false,
    method: 'observation', result: null, evidence_attachments: [], source_ref: { fmea_id: 'f1', cause_node_id: 'cause-1' },
    verified_by: null, verified_at: null, created_at: '2026-10-23T00:00:00Z' }]);
  const post = deferred<any>(); vi.mocked(api.updateVerification).mockReturnValueOnce(post.promise);
  view(<D4VerificationCard capaId="report-A" canEdit currentRootCause="Cause A" fmeaRefId="f1" />);
  if (kind === 'conclusion') fireEvent.click(await screen.findByTestId('verify-pass-0'));
  else { fireEvent.click(await screen.findByTestId('d4-cause-edit-btn-0')); fireEvent.click(screen.getByTestId('d4-cause-save-0')); }
  await waitFor(() => expect(api.updateVerification).toHaveBeenCalled());
  const signal = vi.mocked(api.updateVerification).mock.calls[0][3]!;
  await act(async () => { identity('B'); });
  expect(signal.aborted).toBe(true);
  const reads = vi.mocked(api.listVerifications).mock.calls.length;
  await act(async () => post.reject({ response: { status: 403 } }));
  expect(api.listVerifications).toHaveBeenCalledTimes(reads); expect(notify.success).not.toHaveBeenCalled(); expect(notify.error).not.toHaveBeenCalled();
});

it('D5 cannot toast or reload on a late denied adoption after close', async () => {
  const post = deferred<any>(), onAdopted = vi.fn(); vi.mocked(api.adoptRecommendation).mockReturnValueOnce(post.promise);
  const rendered = view(<D5RecPanel capaId="report-A" onAdopted={onAdopted} />);
  fireEvent.click(await screen.findByTestId('d5-adopt-suggestion'));
  await waitFor(() => expect(api.adoptRecommendation).toHaveBeenCalled());
  const signal = vi.mocked(api.adoptRecommendation).mock.calls[0][2]!;
  rendered.unmount(); expect(signal.aborted).toBe(true);
  await act(async () => post.reject({ response: { status: 403 } }));
  expect(onAdopted).not.toHaveBeenCalled(); expect(notify.success).not.toHaveBeenCalled(); expect(notify.error).not.toHaveBeenCalled();
});

it('a report switch invalidates an old beforeAdopt even when credentials have not changed', async () => {
  const before = deferred<void>(); const onAdopted = vi.fn();
  const rendered = view(<D4RecPanel capaId="report-A" beforeAdopt={() => before.promise} onAdopted={onAdopted} />);
  fireEvent.click(await screen.findByTestId('d4-adopt'));
  rendered.rerender(<App><MemoryRouter><D4RecPanel capaId="report-B" beforeAdopt={() => before.promise} onAdopted={onAdopted} /></MemoryRouter></App>);
  await act(async () => before.resolve());
  expect(api.adoptRecommendation).not.toHaveBeenCalled(); expect(onAdopted).not.toHaveBeenCalled(); expect(notify.error).not.toHaveBeenCalled();
});

it('D7 auto-fill cannot toast or start follow-up reads on late success after credential switch', async () => {
  const post = deferred<any>(); vi.mocked(api.autoFillD7).mockReturnValueOnce(post.promise);
  view(<D7RecPanel capaId="report-A" d5Correction="Implemented" canAdopt canAutoFill onConfirmationChange={vi.fn()} />);
  fireEvent.click(await screen.findByTestId('d7-auto-fill'));
  await waitFor(() => expect(api.autoFillD7).toHaveBeenCalled());
  const signal = vi.mocked(api.autoFillD7).mock.calls[0][2]!;
  await act(async () => { identity('B'); }); expect(signal.aborted).toBe(true);
  const reads = vi.mocked(api.listD7Actions).mock.calls.length;
  await act(async () => post.resolve({}));
  expect(api.listD7Actions).toHaveBeenCalledTimes(reads); expect(notify.success).not.toHaveBeenCalled();
});
