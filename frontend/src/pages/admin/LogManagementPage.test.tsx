import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import LogManagementPage from "./LogManagementPage";

const { listAuditLogs, listLoginLogs, listSystemLogs } = vi.hoisted(() => ({
  listAuditLogs: vi.fn().mockResolvedValue({ items: [{ log_id: "a1", table_name: "fmea_documents", record_id: "r", action: "UPDATE", operated_by: "alice", ip_address: "1.1.1.1", operated_at: "2026-06-26T00:00:00", changed_fields: null, old_values: null, new_values: null }], total: 1, page: 1, page_size: 20 }),
  listLoginLogs: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  listSystemLogs: vi.fn().mockResolvedValue({ items: [{ log_id: "s1", logger_name: "app.x", level: "ERROR", message: "boom", module: "x", traceback: "tb", occurred_at: "2026-06-26T00:00:00" }], total: 1, page: 1, page_size: 20 }),
}));

vi.mock("../../api/logs", () => ({ listAuditLogs, listLoginLogs, listSystemLogs }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe("LogManagementPage", () => {
  it("audit tab loads audit logs and shows row", async () => {
    render(<App><MemoryRouter><LogManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(listAuditLogs).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("fmea_documents")).toBeInTheDocument());
  });

  it("switching to login tab loads login logs", async () => {
    render(<App><MemoryRouter><LogManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(listAuditLogs).toHaveBeenCalled());
    fireEvent.click(screen.getByText("tabs.login"));
    await waitFor(() => expect(listLoginLogs).toHaveBeenCalled());
  });

  it("switching to system tab loads system logs lazily", async () => {
    render(<App><MemoryRouter><LogManagementPage /></MemoryRouter></App>);
    await waitFor(() => expect(listAuditLogs).toHaveBeenCalled());
    expect(listSystemLogs).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("tabs.system"));
    await waitFor(() => expect(listSystemLogs).toHaveBeenCalled());
  });
});
