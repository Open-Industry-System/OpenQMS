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
  byte_size: number | null;
  status: AttachmentStatus;
  scanned_at: string | null;
  expires_at: string;
}
