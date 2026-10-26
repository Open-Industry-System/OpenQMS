import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it } from 'vitest';
import client from './client';
import { getCAPA } from './capa';
import { useAuthStore } from '../store/authStore';
import { useCapaCredentialIdentity, useCapaViewRequests } from '../components/capa/useCapaViewRequests';

const originalAdapter = client.defaults.adapter;
const deferred = <T,>() => { let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
function session(name: string) {
  localStorage.setItem('access_token', `${name}-access`); localStorage.setItem('refresh_token', `${name}-refresh`);
  localStorage.setItem('tenant_slug', name);
  useAuthStore.setState({ token: `${name}-access`, user: { user_id: name, permissions: { capa: 3 } } as any });
}
function owned() {
  return renderHook(() => { const credential = useCapaCredentialIdentity(); return useCapaViewRequests(credential.identity, credential.current); });
}
beforeEach(() => { localStorage.clear(); session('A'); });
afterEach(() => { client.defaults.adapter = originalAdapter; localStorage.clear(); });

it.each(['success', 'denial'])('actual /auth/me late %s for an owned CAPA read cannot mutate or log out B', async outcome => {
  const pending = deferred<any>(); let meConfig: any;
  const seen: string[] = [];
  client.defaults.adapter = async config => {
    seen.push(config.url!);
    if (config.url === '/auth/me') {
      meConfig = config;
      return pending.promise.then(data => ({ data, status: 200, statusText: 'OK', headers: {}, config }));
    }
    throw { config, response: { status: 403, data: {} } };
  };
  const hook = owned(); const request = hook.result.current.begin();
  const result = getCAPA('report-A', request.signal).catch(error => error);
  await waitFor(() => expect(meConfig).toBeDefined());
  await act(async () => { session('B'); });
  const userB = useAuthStore.getState().user;
  await act(async () => outcome === 'success' ? pending.resolve({ user_id: 'A', permissions: { capa: 5 } })
    : pending.reject({ config: meConfig, response: { status: 401, data: {} } }));
  await result;
  expect(useAuthStore.getState().user).toBe(userB);
  expect(useAuthStore.getState().token).toBe('B-access');
  expect(localStorage.getItem('access_token')).toBe('B-access'); expect(localStorage.getItem('refresh_token')).toBe('B-refresh');
  expect(meConfig.signal).toBe(request.signal);
  expect(seen).toEqual(['/capa/report-A', '/auth/me']); hook.unmount();
});

it.each(['success', 'failure'])('actual refresh late %s from A cannot install A credentials or log out B', async outcome => {
  const pending = deferred<any>(); let refreshConfig: any;
  const seen: string[] = [];
  client.defaults.adapter = async config => {
    seen.push(config.url!);
    if (config.url === '/auth/refresh') {
      refreshConfig = config;
      return pending.promise.then(data => ({ data, status: 200, statusText: 'OK', headers: {}, config }));
    }
    throw { config, response: { status: 401, data: {} } };
  };
  const hook = owned(); const request = hook.result.current.begin();
  const result = getCAPA('report-A', request.signal).catch(error => error);
  await waitFor(() => expect(refreshConfig).toBeDefined());
  await act(async () => { session('B'); });
  const userB = useAuthStore.getState().user;
  await act(async () => outcome === 'success' ? pending.resolve({ access_token: 'A-new', refresh_token: 'A-new-refresh' })
    : pending.reject({ config: refreshConfig, response: { status: 401, data: {} } }));
  // Assertions precede awaiting settlement so the old broken refresh queue cannot hide the state corruption behind a timeout.
  expect(useAuthStore.getState().user).toBe(userB);
  expect(useAuthStore.getState().token).toBe('B-access');
  expect(localStorage.getItem('access_token')).toBe('B-access'); expect(localStorage.getItem('refresh_token')).toBe('B-refresh');
  expect(refreshConfig.signal).toBe(request.signal);
  await result;
  expect(seen).toEqual(['/capa/report-A', '/auth/refresh']); hook.unmount();
});

it('unowned business requests retain the existing same-session refresh and replay policy', async () => {
  let attempts = 0;
  client.defaults.adapter = async config => {
    if (config.url === '/auth/refresh') return { config, data: { access_token: 'fresh', refresh_token: 'fresh-refresh' }, headers: {}, status: 200, statusText: 'OK' };
    attempts += 1;
    if (attempts === 1) throw { config, response: { status: 401, data: {} } };
    return { config, data: { ok: true }, headers: {}, status: 200, statusText: 'OK' };
  };
  expect((await client.get('/unrelated-business')).data).toEqual({ ok: true });
  expect(attempts).toBe(2); expect(useAuthStore.getState().token).toBe('fresh');
});


it.each(['tenant_slug', 'access_token', 'refresh_token'])('actual refresh cannot mutate credentials after an unsignalled stored %s change', async key => {
  const pending = deferred<any>(); let refreshConfig: any;
  client.defaults.adapter = async config => {
    if (config.url === '/auth/refresh') {
      refreshConfig = config;
      return pending.promise.then(data => ({ data, config, status: 200, statusText: 'OK', headers: {} }));
    }
    throw { config, response: { status: 401, data: {} } };
  };
  const hook = owned(); const request = hook.result.current.begin();
  const result = getCAPA('report-A', request.signal).catch(error => error);
  await waitFor(() => expect(refreshConfig).toBeDefined());
  // No storage event or React rerender: the transport must consult the origin guard, not just an abort flag.
  localStorage.setItem(key, 'changed-B');
  await act(async () => pending.resolve({ access_token: 'A-new', refresh_token: 'A-new-refresh' }));
  await result;
  expect(localStorage.getItem('access_token')).toBe(key === 'access_token' ? 'changed-B' : 'A-access');
  expect(localStorage.getItem('refresh_token')).toBe(key === 'refresh_token' ? 'changed-B' : 'A-refresh');
  expect(useAuthStore.getState().token).toBe('A-access'); hook.unmount();
});

it('a current owned refresh still releases existing unrelated queued reads without replaying the old view', async () => {
  const pending = deferred<any>(); let refreshConfig: any, unrelatedAttempts = 0;
  client.defaults.adapter = async config => {
    if (config.url === '/auth/refresh') {
      refreshConfig = config;
      return pending.promise.then(data => ({ data, config, headers: {}, status: 200, statusText: 'OK' }));
    }
    if (config.url === '/unrelated-business' && ++unrelatedAttempts > 1) return { data: { ok: true }, config, headers: {}, status: 200, statusText: 'OK' };
    throw { config, response: { status: 401, data: {} } };
  };
  const hook = owned(); const request = hook.result.current.begin();
  const oldView = getCAPA('report-A', request.signal).catch(error => error);
  await waitFor(() => expect(refreshConfig).toBeDefined());
  const unrelated = client.get('/unrelated-business');
  await waitFor(() => expect(unrelatedAttempts).toBe(1));
  await act(async () => pending.resolve({ access_token: 'fresh', refresh_token: 'fresh-refresh' }));
  await oldView;
  expect((await unrelated).data).toEqual({ ok: true });
  expect(unrelatedAttempts).toBe(2); expect(useAuthStore.getState().token).toBe('fresh'); hook.unmount();
});


it('an old child signal cannot enter POST transport with a newly stored credential even before React rerenders', async () => {
  const seen: string[] = [];
  client.defaults.adapter = async config => {
    seen.push(String(config.headers.Authorization));
    return { config, data: {}, status: 200, statusText: 'OK', headers: {} };
  };
  const hook = owned(); const request = hook.result.current.begin();
  localStorage.setItem('access_token', 'B-access');
  expect(request.signal.aborted).toBe(false);
  await expect(client.post('/capa/report-A/adopt-recommendation', { d_step: 'd4', adopted_text: 'old A' }, { signal: request.signal }))
    .rejects.toMatchObject({ name: 'CanceledError' });
  expect(seen).toEqual([]); hook.unmount();
});
