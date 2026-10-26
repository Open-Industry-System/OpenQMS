// Only explicitly owned CAPA view requests opt in. Unrelated routes keep their
// existing refresh policy; this registry stores lifetimes, never result content.
const owners = new WeakMap<object, () => boolean>();
export function registerCapaRequest(signal: AbortSignal, current: () => boolean) {
  owners.set(signal, current);
}
export function capaRequestOwner(signal?: object): (() => boolean) | undefined {
  return signal ? owners.get(signal) : undefined;
}
