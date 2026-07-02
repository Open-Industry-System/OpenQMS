const created: { kind: string; id: string }[] = [];

export function track(kind: string, id: string): void {
  created.push({ kind, id });
}

export function drainReport(): void {
  if (created.length) {
    // eslint-disable-next-line no-console
    console.warn(`[cleanup] un-cleaned records:`, created);
  }
}

let counter = 0;
export function nextDocNo(prefix: string): string {
  counter += 1;
  return `${prefix}-${String(counter).padStart(3, "0")}`;
}
