export type AttachmentStatus =
  | "scanning"
  | "promoting"
  | "available"
  | "rejected_malware"
  | "rejected_scanner"
  | "failed_storage"
  | "purging"
  | "purged";

export interface AgentTaskAttachment {
  attachment_id: string;
  display_name: string | null;
  extension: string | null;
  byte_size: number | null;
  status: AttachmentStatus;
  created_at: string;
  updated_at: string;
  expires_at: string;
}
