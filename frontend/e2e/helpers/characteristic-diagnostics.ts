export interface HttpFailure {
  method: string;
  url: string;
  status: number;
}

export function isDisabledAgentProbe(response: HttpFailure, uiURL: string): boolean {
  if (response.method !== "GET" || response.status !== 404) return false;
  try {
    const url = new URL(response.url);
    return url.origin === new URL(uiURL).origin
      && url.pathname === "/api/agent/tasks/availability"
      && !url.search && !url.hash && !url.username && !url.password;
  } catch {
    return false;
  }
}

export function unexpectedCharacteristicFailures(
  responses: HttpFailure[], uiURL: string, allowSyncConflict: boolean,
): HttpFailure[] {
  return responses.filter(response => !isDisabledAgentProbe(response, uiURL)
    && !(allowSyncConflict && response.status === 409));
}

export function isDisabledAgentProbeConsole(
  message: string, url: string, responses: HttpFailure[], uiURL: string,
): boolean {
  if (!message.includes("status of 404 (Not Found)")) return false;
  const attributed = responses.filter(response => response.url === url);
  return attributed.length > 0 && attributed.every(response => isDisabledAgentProbe(response, uiURL));
}
