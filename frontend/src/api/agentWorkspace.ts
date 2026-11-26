import client from "./client";

export interface WorkspacePage {
  kind: "capa";
  report_id: string;
}

interface WorkspaceDocument {
  id: string;
  document_no: string;
  title: string;
}

export type WorkspaceResult =
  | { kind: "assistant"; id: string; content: string }
  | { kind: "pfmea_list"; id: string; items: WorkspaceDocument[] }
  | {
      kind: "draft_preview";
      id: string;
      preview: {
        title: string;
        document_no: string;
        factory_name: string;
        product_line_name: string;
        source_document_no: string;
        fmea_type: "PFMEA";
      };
    };

export type WorkspaceConversationItem = WorkspaceResult | { kind: "user"; id: string; content: string };

export interface WorkspaceTurn {
  conversation_id?: string;
  request_id: string;
  page: WorkspacePage;
  content: string;
}

export type WorkspaceActionResult =
  | { status: "applied"; draft: WorkspaceDocument }
  | { status: "cancelled" };

const path = "/agent/workspace";

export async function getWorkspaceAvailability(page: WorkspacePage | null, signal: AbortSignal) {
  const response = await client.get<{ enabled: boolean; context?: { document_no: string } }>(
    `${path}/availability`,
    { signal, params: { report_id: page?.report_id } },
  );
  return response.data;
}

export async function getWorkspaceConversation(conversationId: string, page: WorkspacePage, signal: AbortSignal) {
  const response = await client.get<{ conversation_id: string; items: WorkspaceConversationItem[] }>(
    `${path}/conversations/${encodeURIComponent(conversationId)}`,
    { signal, params: { report_id: page.report_id } },
  );
  return response.data;
}

export async function sendWorkspaceTurn(body: WorkspaceTurn, factoryId: string | null, signal: AbortSignal) {
  const response = await client.post<{ conversation_id: string; items: WorkspaceResult[] }>(
    `${path}/turn`,
    body,
    { signal, params: { factory_id: factoryId ?? undefined }, timeout: 120_000 },
  );
  return response.data;
}

export async function resolveWorkspaceAction(
  actionId: string,
  operation: "confirm" | "cancel",
  body: { conversation_id: string; page: WorkspacePage },
  factoryId: string | null,
  signal: AbortSignal,
) {
  const response = await client.post<WorkspaceActionResult>(
    `${path}/actions/${encodeURIComponent(actionId)}/${operation}`,
    body,
    { signal, params: { factory_id: factoryId ?? undefined } },
  );
  return response.data;
}
