import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import client from '../../api/client';
import { useAuthStore } from '../../store/authStore';
import { useProductLineStore } from '../../store/productLineStore';
import D4TextRedactionPreview from './D4TextRedactionPreview';

const id = '00000000-0000-4000-8000-000000000001';
const original = client.defaults.adapter;
let version: () => Promise<unknown>, create: () => Promise<unknown>, calls: string[];
function candidate() {
  return { report_id: id, rule_version: 'capa.d4.redaction.v1', source_version: 'a'.repeat(64),
    generated_at: new Date(Date.now()).toISOString(), expires_at: new Date(Date.now()+30000).toISOString(),
    data_class: 'restricted', projection: 'redaction_candidate', declassification_status: 'not_approved',
    external_delivery_allowed: false, fields: [{ field: 'd4_root_cause', verification_id: null,
      redacted_text: '受限技术叙述 <img src=x onerror=alert(1)>', source_status: 'unverified', source_ref: null, match_counts: {} }] };
}
async function flush() { await act(async () => { for (let i=0;i<8;i++) await Promise.resolve(); }); }
async function open() {
  await flush();
  fireEvent.click(screen.getByRole('button', { name: '正文脱敏候选预览' }));
  await flush();
}
async function generate() {
  fireEvent.click(screen.getByRole('button', { name: '生成受限候选' }));
  await flush();
}
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2030-01-01T00:00:00Z'));
  localStorage.clear(); localStorage.setItem('access_token', 'employee-jwt');
  useAuthStore.setState({ user: { user_id: id } as any, token: 'employee-jwt', currentFactoryId: id });
  useProductLineStore.setState({ selected: 'LINE' });
  calls = [];
  version = async () => ({ report_id: id, rule_version: 'capa.d4.redaction.v1', source_version: 'a'.repeat(64) });
  create = async () => candidate();
  client.defaults.adapter = async config => {
    calls.push(config.url!);
    try {
      const data = config.url!.endsWith('/availability') ? { enabled: true }
        : config.url!.endsWith('/version') ? await version() : await create();
      return { data, status: 200, statusText: 'OK', headers: {}, config };
    } catch (error) {
      // Actual Axios errors preserve the failed request config for endpoint guards.
      throw { ...(error as object), config };
    }
  };
});
afterEach(() => { cleanup(); client.defaults.adapter = original; vi.useRealTimers(); vi.restoreAllMocks(); });
it('does no body fetch before explicit generation and renders text without editing or persistence', async () => {
  const writes = vi.spyOn(Storage.prototype, 'setItem');
  const view = render(<D4TextRedactionPreview reportId={id} />);
  await open();
  expect(calls).toEqual([`/capa/${id}/d4-text-preview/availability`]);
  await generate();
  expect(screen.getByText(/受限技术叙述/)).toBeVisible();
  expect(document.querySelector('img[src="x"]')).toBeNull();
  expect(screen.queryByRole('button', { name: /替换|采纳|保存/ })).toBeNull();
  expect(writes).not.toHaveBeenCalled();
  view.unmount();
});
it.each(['network','version','denial'])('withdraws content on %s uncertainty at the next version check', async damage => {
  render(<D4TextRedactionPreview reportId={id} />); await open();
  fireEvent.change(screen.getByRole('textbox', { name: '显式替换词' }), { target: { value: 'PRIVATE TERM' } });
  await generate();
  expect(screen.getByText(/受限技术叙述/)).toBeVisible();
  version = async () => {
    if (damage === 'version') return { report_id: id, rule_version: 'capa.d4.redaction.v1', source_version: 'b'.repeat(64) };
    throw { response: damage === 'denial' ? { status: 403 } : undefined };
  };
  await act(() => vi.advanceTimersByTimeAsync(2000)); await flush();
  expect(screen.queryByText(/受限技术叙述/)).toBeNull();
  expect(screen.getByRole('textbox', { name: '显式替换词' })).toHaveValue('');
});
it('expires independently of network progress and clears terms on close', async () => {
  render(<D4TextRedactionPreview reportId={id} />); await open();
  fireEvent.change(screen.getByRole('textbox', { name: '显式替换词' }), { target: { value: 'PRIVATE TERM' } });
  await generate();
  version = () => new Promise(() => {});
  await act(() => vi.advanceTimersByTimeAsync(30001)); await flush();
  expect(screen.queryByText(/受限技术叙述/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '关闭预览' })); await flush();
  await open();
  expect(screen.getByRole('textbox', { name: '显式替换词' })).toHaveValue('');
});
it('client clock skew cannot extend the local 30 second candidate lifetime', async () => {
  create = async () => {
    const value = candidate();
    value.generated_at = new Date(Date.now()+600000).toISOString();
    value.expires_at = new Date(Date.now()+630000).toISOString();
    return value;
  };
  render(<D4TextRedactionPreview reportId={id} />); await open(); await generate();
  version = () => new Promise(() => {});
  await act(() => vi.advanceTimersByTimeAsync(30001)); await flush();
  expect(screen.queryByText(/受限技术叙述/)).toBeNull();
});
it('draft changes clear content and late old responses cannot republish after a target change', async () => {
  const view = render(<D4TextRedactionPreview reportId={id} />); await open(); await generate();
  fireEvent.change(screen.getByRole('textbox', { name: '显式替换词' }), { target: { value: 'NEW' } });
  expect(screen.queryByText(/受限技术叙述/)).toBeNull();
  let release!: (value: unknown) => void;
  create = () => new Promise(resolve => { release = resolve; });
  fireEvent.click(screen.getByRole('button', { name: '生成受限候选' })); await flush();
  view.rerender(<D4TextRedactionPreview reportId="00000000-0000-4000-8000-000000000002" />);
  await flush(); release(candidate()); await flush();
  expect(screen.queryByText(/受限技术叙述/)).toBeNull();
});
it('hiding withdraws body and stops version polling', async () => {
  render(<D4TextRedactionPreview reportId={id} />); await open(); await generate();
  Object.defineProperty(document, 'hidden', { configurable: true, value: true });
  fireEvent(document, new Event('visibilitychange')); await flush();
  expect(screen.queryByText(/受限技术叙述/)).toBeNull();
  const count = calls.length;
  await act(() => vi.advanceTimersByTimeAsync(4000));
  expect(calls).toHaveLength(count);
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
});
