import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { App } from "antd";
import FMEAListPage from "./FMEAListPage";
import i18n from "../../../i18n";

// vi.mock factory 被 hoist，必须用 vi.hoisted 暴露 mock 函数给测试体引用
const mocks = vi.hoisted(() => ({
  listFMEAs: vi.fn(),
  createFMEA: vi.fn(),
}));

vi.mock("../../../api/fmea", () => ({
  listFMEAs: mocks.listFMEAs,
  createFMEA: mocks.createFMEA,
}));

// store 以 selector 方式调用，mock 必须执行 selector
vi.mock("../../../store/authStore", () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) =>
    selector({ user: { user_id: "u1", role: "admin" } }),
}));

vi.mock("../../../hooks/usePermission", () => ({
  usePermission: () => ({ canEdit: () => true }),
}));

vi.mock("../../../store/productLineStore", () => ({
  useProductLineStore: (selector: (s: { selected: string }) => unknown) =>
    selector({ selected: "DC-DC-100" }),
}));

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

function renderAt(path: string) {
  return render(
    <App>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/fmea" element={<FMEAListPage />} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listFMEAs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
});

describe("FMEAListPage filters", () => {
  it("renders without crashing and requests first page", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());
  });

  it("reads legacy ?risk=high and sends high_rpn=true", async () => {
    renderAt("/fmea?risk=high");
    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.high_rpn).toBe(true);
    });
  });

  it("reads legacy ?pending_approval=true and sends status=in_review", async () => {
    renderAt("/fmea?pending_approval=true");
    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.status).toBe("in_review");
    });
  });

  it("changing type filter sends fmea_type and resets to page 1", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    // antd 5 Select opens on mouseDown of the .ant-select-selector (not the inner
    // combobox input). The filter bar renders two selects (status, type); the
    // modal's type select is not mounted while the modal is closed.
    // The option's visible text lives in a child .ant-select-item-option-content
    // span, so getByText can't target the clickable option element reliably —
    // query the .ant-select-item-option element directly by its textContent.
    const typeSelectSelector = document.querySelectorAll(".ant-select-selector")[1];
    fireEvent.mouseDown(typeSelectSelector);
    let option: HTMLElement | undefined;
    await vi.waitFor(() => {
      option = Array.from(
        document.querySelectorAll<HTMLElement>(".ant-select-item-option")
      ).find((el) => el.textContent === "DFMEA");
      expect(option).toBeTruthy();
    });
    fireEvent.mouseDown(option!);
    fireEvent.click(option!);

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.fmea_type).toBe("DFMEA");
      expect(call.page).toBe(1);
    });
  });

  it("search onSearch sends search param", async () => {
    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const searchInput = screen.getByPlaceholderText(/search|搜索/i);
    fireEvent.change(searchInput, { target: { value: "焊接" } });
    fireEvent.keyDown(searchInput, { key: "Enter", code: "Enter" });

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.search).toBe("焊接");
    });
  });

  it("reset clears all filters incl. legacy params and requests unfiltered list", async () => {
    // 初始 URL 同时含新参数与旧兼容参数 risk / pending_approval
    renderAt("/fmea?status=draft&type=PFMEA&high_rpn=true&search=foo&risk=high&pending_approval=true");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const resetBtn = screen.getByRole("button", { name: /reset|重置/i });
    fireEvent.click(resetBtn);

    await vi.waitFor(() => {
      const call = mocks.listFMEAs.mock.calls[mocks.listFMEAs.mock.calls.length - 1][0];
      expect(call.status).toBeUndefined();
      expect(call.fmea_type).toBeUndefined();
      expect(call.high_rpn).toBeUndefined();
      expect(call.search).toBeUndefined();
    });
  });
});

describe("FMEAListPage create error", () => {
  // 复用 list mock 默认值，避免 beforeEach 的 module 级状态污染
  beforeEach(async () => {
    mocks.listFMEAs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    // 锁定中文，断言本地化文案（而非英文 detail 透传）
    await i18n.changeLanguage("zh-CN");
  });

  it("maps duplicate document_no error to a localized Chinese message", async () => {
    // 后端在文档编号重复时返回 400 + 英文 detail，见 fmea_service.create_fmea
    const detail = "FMEA document number 'PFMEA-2026-001' already exists.";
    mocks.createFMEA.mockRejectedValueOnce({
      response: { status: 400, data: { detail } },
    });

    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    // 打开新建弹窗
    fireEvent.click(await screen.findByRole("button", { name: /new fmea|新建/i }));

    // 占位符在两种语言下都含 "PFMEA-2026-001" / "SMT"，可稳定定位
    const docNoInput = await screen.findByPlaceholderText(/PFMEA-2026-001/i);
    fireEvent.change(docNoInput, { target: { value: "PFMEA-2026-001" } });
    const titleInput = await screen.findByPlaceholderText(/SMT/i);
    fireEvent.change(titleInput, { target: { value: "测试标题" } });

    // 提交（antd Modal 默认 OK 按钮）
    fireEvent.click(screen.getByRole("button", { name: /^ok$/i }));

    await vi.waitFor(() => expect(mocks.createFMEA).toHaveBeenCalled());
    // 前端映射后：英文 detail → 中文「文档编号「PFMEA-2026-001」已存在…」
    await vi.waitFor(() => {
      expect(screen.getByText(/文档编号「PFMEA-2026-001」已存在/)).toBeInTheDocument();
    });
  });
});

describe("FMEAListPage create navigation", () => {
  beforeEach(() => {
    mocks.listFMEAs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  });

  it("navigates to DFMEA wizard on create fmea_type=DFMEA", async () => {
    mocks.createFMEA.mockResolvedValue({ fmea_id: "dfmea-1", fmea_type: "DFMEA" });

    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole("button", { name: /new fmea|新建/i }));

    // 选择 DFMEA：modal 中 type Select 的 option 文案是完整中文全称，匹配开头 "DFMEA -"
    const typeSelectSelector = document.querySelectorAll(".ant-select-selector")[2];
    fireEvent.mouseDown(typeSelectSelector!);
    let option: HTMLElement | undefined;
    await vi.waitFor(() => {
      option = Array.from(document.querySelectorAll<HTMLElement>(".ant-select-item-option"))
        .find((el) => el.textContent?.startsWith("DFMEA"));
      expect(option).toBeTruthy();
    });
    fireEvent.mouseDown(option!);
    fireEvent.click(option!);

    const docNoInput = await screen.findByPlaceholderText(/PFMEA-2026-001/i);
    fireEvent.change(docNoInput, { target: { value: "DFMEA-2026-002" } });
    const titleInput = await screen.findByPlaceholderText(/SMT/i);
    fireEvent.change(titleInput, { target: { value: "DFMEA 标题" } });

    fireEvent.click(screen.getByRole("button", { name: /^ok$/i }));

    await vi.waitFor(() => expect(mocks.createFMEA).toHaveBeenCalled());
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/fmea/wizard/dfmea-1"));
  });

  it("navigates to PFMEA wizard on create fmea_type=PFMEA", async () => {
    mocks.createFMEA.mockResolvedValue({ fmea_id: "pfmea-1", fmea_type: "PFMEA" });

    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole("button", { name: /new fmea|新建/i }));

    const docNoInput = await screen.findByPlaceholderText(/PFMEA-2026-001/i);
    fireEvent.change(docNoInput, { target: { value: "PFMEA-2026-002" } });
    const titleInput = await screen.findByPlaceholderText(/SMT/i);
    fireEvent.change(titleInput, { target: { value: "PFMEA 标题" } });

    fireEvent.click(screen.getByRole("button", { name: /^ok$/i }));

    await vi.waitFor(() => expect(mocks.createFMEA).toHaveBeenCalled());
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/fmea/pfmea-wizard/pfmea-1"));
  });
});

describe("FMEAListPage draft navigation", () => {
  it("routes DFMEA incomplete drafts to the DFMEA wizard", async () => {
    mocks.listFMEAs.mockResolvedValue({
      items: [{
        fmea_id: "dfmea-draft-1",
        document_no: "DFMEA-2026-D1",
        title: "DFMEA draft",
        fmea_type: "DFMEA",
        status: "draft",
        version: 1,
        updated_at: new Date().toISOString(),
        graph_data: { wizardScope: { wizard_completed: false } },
      }],
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const editBtn = await screen.findByRole("button", { name: /edit|编辑/i });
    fireEvent.click(editBtn);

    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/fmea/wizard/dfmea-draft-1"));
  });

  it("routes PFMEA incomplete drafts to the PFMEA wizard", async () => {
    mocks.listFMEAs.mockResolvedValue({
      items: [{
        fmea_id: "pfmea-draft-1",
        document_no: "PFMEA-2026-D1",
        title: "PFMEA draft",
        fmea_type: "PFMEA",
        status: "draft",
        version: 1,
        updated_at: new Date().toISOString(),
        graph_data: { wizardScope: { wizard_completed: false } },
      }],
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderAt("/fmea");
    await vi.waitFor(() => expect(mocks.listFMEAs).toHaveBeenCalled());

    const editBtn = await screen.findByRole("button", { name: /edit|编辑/i });
    fireEvent.click(editBtn);

    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/fmea/pfmea-wizard/pfmea-draft-1"));
  });
});
