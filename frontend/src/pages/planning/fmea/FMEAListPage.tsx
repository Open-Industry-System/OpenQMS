import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Tag, Form, Input, Select, Switch, Space, Modal, App } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listFMEAs, createFMEA } from "../../../api/fmea";
import type { FMEADocument } from "../../../types";
import { useAuthStore } from "../../../store/authStore";
import { usePermission } from "../../../hooks/usePermission";
import { useProductLineStore } from "../../../store/productLineStore";
import { PageShell, StatusBadge } from "../../../components/design";

export default function FMEAListPage() {
  const { t, i18n } = useTranslation("fmea");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();

  const typeLabels: Record<string, string> = {
    PFMEA: "PFMEA",
    DFMEA: "DFMEA",
  };

  const statusLabels: Record<string, string> = {
    draft: t("status.draft"),
    in_review: t("status.in_review"),
    approved: t("status.approved"),
    rework: t("status.rework"),
    archived: t("status.archived"),
  };
  const [data, setData] = useState<FMEADocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();
  const productLine = useProductLineStore((s) => s.selected);
  const [searchParams, setSearchParams] = useSearchParams();

  // 本地搜索框值：键入即时显示，仅 onSearch 时写 URL，避免输入滞后
  const [searchInput, setSearchInput] = useState("");

  // 统一筛选读取来源（受控控件初始值 + 请求组装共用），含旧参数回退
  const filterStatus = searchParams.get("status")
    ?? (searchParams.get("pending_approval") === "true" ? "in_review" : null);
  // 运行时 normalize：只有 PFMEA/DFMEA 才传，避免 ?type=foo 发到后端触发 422
  const rawType = searchParams.get("type");
  const filterType = rawType === "PFMEA" || rawType === "DFMEA" ? rawType : null;
  const filterHighRpn = searchParams.get("high_rpn") === "true"
    || searchParams.get("risk") === "high";
  const filterSearch = searchParams.get("search");

  // 外部 URL 变化（初始化/后退/重置）时同步本地搜索框。
  // 此 effect 只依赖 filterSearch、只更新本地 searchInput，绝不触发请求；
  // 请求只由下面的 [productLine, searchParams] effect 触发。
  // 勿把搜索输入变化接入请求——输入只改 searchInput，请求经 onSearch 写 URL 后由 searchParams 变化驱动。
  useEffect(() => {
    setSearchInput(filterSearch ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterSearch]);

  const fetchData = (p: number = page) => {
    setLoading(true);
    listFMEAs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      status: filterStatus || undefined,
      fmea_type: filterType || undefined,
      high_rpn: filterHighRpn || undefined,
      search: filterSearch || undefined,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  // 写回 URL：空值/关闭态一律剔除参数（含旧参数），保持 URL 简洁
  const updateFilters = (next: Record<string, string | null>) => {
    const params = new URLSearchParams(searchParams);
    // 清掉旧兼容参数，统一用新名
    params.delete("risk");
    params.delete("pending_approval");
    for (const [key, val] of Object.entries(next)) {
      if (val) params.set(key, val);
      else params.delete(key);
    }
    setSearchParams(params, { replace: true });
    setPage(1);
  };

  const onStatusChange = (v: string | null) => updateFilters({ status: v ?? null });
  const onTypeChange = (v: string | null) => updateFilters({ type: v ?? null });
  const onHighRpnChange = (checked: boolean) => updateFilters({ high_rpn: checked ? "true" : null });
  const onSearch = (value: string) => updateFilters({ search: value.trim() || null });

  const onReset = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("status");
    params.delete("type");
    params.delete("search");
    params.delete("high_rpn");
    params.delete("risk");
    params.delete("pending_approval");
    setSearchParams(params, { replace: true });
    setSearchInput("");
    setPage(1);
  };

  useEffect(() => {
    setPage(1);
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine, searchParams]);

  const handleCreate = async (values: { title: string; document_no: string; fmea_type: string; problem_description?: string }) => {
    try {
      const fmea = await createFMEA(values);
      message.success(t("messages.createSuccess"));
      setModalOpen(false);
      form.resetFields();
      if (values.fmea_type === "DFMEA") {
        navigate(`/fmea/wizard/${fmea.fmea_id}`);
      } else {
        navigate(`/fmea/${fmea.fmea_id}`, { state: { showLessonsLearned: true, problemDescription: values.problem_description } });
      }
    } catch {
      message.error(t("messages.createFailed"));
    }
  };

  const columns = [
    {
      title: t("list.columns.documentNo"),
      dataIndex: "document_no",
      key: "document_no",
      width: 150,
      render: (v: string) => <span style={{ fontFamily: "var(--qf-font-mono)" }}>{v}</span>,
    },
    { title: t("list.columns.title"), dataIndex: "title", key: "title", ellipsis: true },
    {
      title: t("list.columns.type"),
      dataIndex: "fmea_type",
      key: "fmea_type",
      width: 90,
      render: (t: string) => (
        <Tag style={{ background: "var(--qf-cyan-dim)", color: "var(--qf-cyan)", borderColor: "var(--qf-cyan)" }}>
          {typeLabels[t] || t}
        </Tag>
      ),
    },
    {
      title: t("list.columns.status"),
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (s: string) => <StatusBadge status={s}>{statusLabels[s] || s}</StatusBadge>,
    },
    {
      title: t("list.columns.version"),
      dataIndex: "version",
      key: "version",
      width: 70,
      render: (v: number) => <span className="qf-mono">v{v}</span>,
    },
    {
      title: t("list.columns.updatedAt"),
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (v: string) => new Date(v).toLocaleString(i18n.language || "zh-CN"),
    },
    {
      title: t("list.columns.actions"),
      key: "actions",
      width: 100,
      render: (_: unknown, record: FMEADocument) => {
        // Only send incomplete DFMEA drafts back to the wizard; completed drafts (wizard_completed)
        // open directly in the editor, matching FMEAEditorPage's redirect guard.
        const isIncompleteDraft = record.fmea_type === "DFMEA" && record.status === "draft"
          && !record.graph_data?.wizardScope?.wizard_completed;
        const targetPath = isIncompleteDraft
          ? `/fmea/wizard/${record.fmea_id}`
          : `/fmea/${record.fmea_id}`;
        return (
          <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(targetPath)}>
            {canEdit('fmea') ? tc("actions.edit") : tc("actions.view")}
          </Button>
        );
      },
    },
  ];

  const actions = canEdit('fmea') ? (
    <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
      {t("list.newFMEA")}
    </Button>
  ) : null;

  return (
    <PageShell title={t("list.title")} subtitle={t("list.subtitle")} actions={actions}>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          style={{ width: 140 }}
          allowClear
          placeholder={t("filter.status")}
          value={filterStatus || undefined}
          onChange={onStatusChange}
          options={[
            { value: "draft", label: t("status.draft") },
            { value: "in_review", label: t("status.in_review") },
            { value: "approved", label: t("status.approved") },
            { value: "rework", label: t("status.rework") },
            { value: "archived", label: t("status.archived") },
          ]}
        />
        <Select
          style={{ width: 140 }}
          allowClear
          placeholder={t("filter.type")}
          value={filterType || undefined}
          onChange={onTypeChange}
          options={[
            { value: "PFMEA", label: "PFMEA" },
            { value: "DFMEA", label: "DFMEA" },
          ]}
        />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Switch
            checked={filterHighRpn}
            onChange={onHighRpnChange}
            aria-label={t("filter.highRisk")}
          />
          {t("filter.highRisk")}
        </span>
        <Input.Search
          style={{ width: 240 }}
          allowClear
          placeholder={t("filter.searchPlaceholder")}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onSearch={onSearch}
        />
        <Button onClick={onReset}>{t("filter.reset")}</Button>
      </Space>
      <Table
        className="qf-table"
        columns={columns}
        dataSource={data}
        rowKey="fmea_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p);
          },
        }}
      />

      <Modal
        title={t("create.title")}
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        okButtonProps={{ className: "qf-btn-primary" }}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ fmea_type: "PFMEA" }}>
          <Form.Item name="fmea_type" label={t("create.type")} rules={[{ required: true, message: t("create.typeRequired") }]}>
            <Select
              options={[
                { value: "PFMEA", label: t("list.typeOption.pfmea") },
                { value: "DFMEA", label: t("list.typeOption.dfmea") },
              ]}
            />
          </Form.Item>
          <Form.Item name="document_no" label={t("create.documentNo")} rules={[{ required: true, message: t("create.documentNoRequired") }]}>
            <Input placeholder={t("create.documentNoPlaceholder")} />
          </Form.Item>
          <Form.Item name="title" label={t("create.titleLabel")} rules={[{ required: true, message: t("create.titleRequired") }]}>
            <Input placeholder={t("create.titlePlaceholder")} />
          </Form.Item>
          <Form.Item name="problem_description" label={t("create.problemDescription")}>
            <Input.TextArea rows={2} placeholder={t("create.problemDescriptionPlaceholder")} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
