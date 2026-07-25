const created: { kind: string; id: string }[] = [];

export function drainReport(): void {
  if (created.length) {
    // eslint-disable-next-line no-console
    console.warn(`[cleanup] un-cleaned records:`, created);
  }
}
