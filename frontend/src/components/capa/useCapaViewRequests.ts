import { useEffect, useMemo, useRef, useState } from 'react';

import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";

/** Local view lifetime only. No material, credential or result is persisted. */
export function useCapaViewRequests(identity: string, credentialsCurrent: () => boolean = () => true) {
  const guard = useRef(credentialsCurrent);
  guard.current = credentialsCurrent;
  const latest = useRef(identity);
  latest.current = identity;
  const scope = useMemo(() => {
    let epoch = 0;
    let active = true;
    const controllers = new Set<AbortController>();
    const invalidate = () => {
      epoch += 1;
      controllers.forEach(controller => controller.abort());
      controllers.clear();
    };
    return {
      invalidate,
      activate: () => { active = true; },
      dispose: () => { active = false; invalidate(); },
      begin: () => {
        const captured = epoch;
        const controller = new AbortController();
        controllers.add(controller);
        return {
          signal: controller.signal,
          current: () => active && guard.current() && latest.current === identity && epoch === captured && !controller.signal.aborted,
          finish: () => { controllers.delete(controller); },
          cancel: () => { controller.abort(); controllers.delete(controller); },
        };
      },
    };
  }, [identity]);
  useEffect(() => {
    scope.activate();
    return () => scope.dispose();
  }, [scope]);
  return scope;
}


// Read existing identity stores; this is not a business-data cache or auth policy.
export function useCapaCredentialIdentity() {
  const auth = useAuthStore();
  const line = useProductLineStore(state => state.selected);
  const [, render] = useState(0);
  const stored = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
  const tenantId = stored('tenant_slug'), storedToken = stored('access_token'), storedFactory = stored('current_factory_id');
  useEffect(() => {
    const changed = () => render(value => value + 1);
    window.addEventListener('storage', changed);
    window.addEventListener('focus', changed);
    return () => { window.removeEventListener('storage', changed); window.removeEventListener('focus', changed); };
  }, []);
  const identity = JSON.stringify([auth.user, auth.token, auth.currentFactoryId, auth.factoryScope, line, tenantId, storedToken, storedFactory]);
  const current = () => {
    const now = useAuthStore.getState();
    return now.user === auth.user && now.token === auth.token && now.currentFactoryId === auth.currentFactoryId
      && now.factoryScope === auth.factoryScope && useProductLineStore.getState().selected === line && stored('tenant_slug') === tenantId && stored('access_token') === storedToken && stored('current_factory_id') === storedFactory;
  };
  return { identity, current };
}
