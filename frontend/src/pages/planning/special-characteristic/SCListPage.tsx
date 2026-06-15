import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Table, Button, Space, Select, Popconfirm, App, Switch,
} from "antd";
import {
  PlusOutlined, FileTextOutlined, DeleteOutlined, TableOutlined,
  SafetyCertificateOutlined, ExclamationCircleOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  listSCs, deleteSC, safetyConfirm, safetyDismiss,
} from "../../../api/specialCharacteristic";
import type { SpecialCharacteristic } from "../../../types";
import { usePermission } from "../../../hooks/usePermission";
import { useProductLineStore } from "../../../store/productLineStore";
import { PageShell, DataCard, StatusBadge } from "../../../components/design";

const scTypeVariant = (t: string): string => (t === "CC" ? "error" : "warning");
const sourceTypeVariant = (t: string): string => (t === "DFMEA" ? "info" : "success");
const msaStatusVariant = (s: string): string => {
  if (s === "PASS") return "success";
  if (s === "FAIL") return "error";
  return "warning";
};

export default function SCListPage() {
  const { t } = useTranslation("specialCharacteristic");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const [data, setData] = useState<SpecialCharacteristic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [scTypeFilter, setScTypeFilter] = useState<string>("");
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>("");
  const [searchParams] = useSearchParams();
  const [safetyRelatedOnly, setSafetyRelatedOnly] = useState(searchParams.get("safety_related_only") === "true");
  const [approvalStatusFilter, setApprovalStatusFilter] = useState<string>(searchParams.get("approval_status") || "");
  const [suggestedOnly, setSuggestedOnly] = useState(searchParams.get("suggested_only") === "true");
  const navigate = useNavigate();

  const { canEdit } = usePermission();
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = (p: number = page) => {
    setLoading(true);
    listSCs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      sc_type: scTypeFilter || undefined,
      source_type: sourceTypeFilter || undefined,
      safety_related_only: safetyRelatedOnly,
      approval_status: approvalStatusFilter || undefined,
      suggested_only: suggestedOnly,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scTypeFilter, sourceTypeFilter, productLine, safetyRelatedOnly, approvalStatusFilter, suggestedOnly]);

  const handleDelete = async (id: string) => {
    try {
      await deleteSC(id);
      message.success(tc("messages.deleteSuccess"));
      fetchData();
    } catch {
      message.error(tc("messages.deleteFailed"));
    }
  };

  const handleSafetyConfirm = async (id: string) => {
    try {
      await safetyConfirm(id);
      message.success(t("message.confirmSafetySuccess"));
      fetchData();
    } catch {
      message.error(t("message.confirmSafetyFailed"));
    }
  };

  const handleSafetyDismiss = async (id: string) => {
    try {
      await safetyDismiss(id);
      message.success(t("message.dismissSuccess"));
      fetchData();
    } catch {
      message.error(t("message.dismissFailed"));
    }
  };

  const columns = [
    {
      title: t("column.scCode"),
      dataIndex: "sc_code",
      key: "sc_code",
      width: 140,
    },
    {
      title: t("column.name"),
      dataIndex: "sc_name",
      key: "sc_name",
      ellipsis: true,
    },
    {
      title: t("column.type"),
      dataIndex: "sc_type",
      key: "sc_type",
      width: 100,
      render: (t: string, record: SpecialCharacteristic) => (
        <Space>
          <StatusBadge status={scTypeVariant(t)}>{t}</StatusBadge>
          {record.is_safety_related && (
            <SafetyCertificateOutlined style={{ color: "#ff4d4f", fontSize: 16 }} />
          )}
          {record.is_safety_suggested && !record.is_safety_related && (
            <ExclamationCircleOutlined style={{ color: "#faad14", fontSize: 16 }} />
          )}
        </Space>
      ),
    },
    {
      title: t("column.customerSymbol"),
      dataIndex: "customer_symbol",
      key: "customer_symbol",
      width: 100,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("column.category"),
      dataIndex: "sc_category",
      key: "sc_category",
      width: 120,
      render: (v: string | null) => (v ? t(`category.${v}`) : "-"),
    },
    {
      title: t("column.sourceType"),
      dataIndex: "source_type",
      key: "source_type",
      width: 100,
      render: (t: string) => (
        <StatusBadge status={sourceTypeVariant(t)}>{t}</StatusBadge>
      ),
    },
    {
      title: t("column.sourceFMEA"),
      dataIndex: "source_fmea_document_no",
      key: "source_fmea_document_no",
      width: 160,
      render: (docNo: string | null, record: SpecialCharacteristic) =>
        docNo ? (
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/fmea/${record.source_fmea_id}`)}
          >
            {docNo}
          </Button>
        ) : (
          "-"
        ),
    },
    {
      title: t("column.msaStatus"),
      dataIndex: "msa_status",
      key: "msa_status",
      width: 100,
      render: (s: string) => (
        <StatusBadge status={msaStatusVariant(s)}>{s}</StatusBadge>
      ),
    },
    {
      title: t("column.actions"),
      key: "actions",
      width: 280,
      render: (_: unknown, record: SpecialCharacteristic) => (
        <Space>
          <Button
            type="link"
            icon={<FileTextOutlined />}
            onClick={() => navigate(`/special-characteristics/${record.sc_id}`)}
          >
            {tc("actions.view")}
          </Button>
          {record.is_safety_suggested && !record.is_safety_related && canEdit('special_characteristic') && (
            <>
              <Button type="link" size="small" onClick={() => handleSafetyConfirm(record.sc_id)}>
                {t("actions.confirmSafety")}
              </Button>
              <Button type="link" size="small" danger onClick={() => handleSafetyDismiss(record.sc_id)}>
                {t("actions.dismiss")}
              </Button>
            </>
          )}
          {canEdit('special_characteristic') && (
            <Popconfirm
              title={t("confirm.delete")}
              onConfirm={() => handleDelete(record.sc_id)}
            >
              <Button type="link" danger icon={<DeleteOutlined />}>
                {tc("actions.delete")}
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageShell
      title={<>
        <TableOutlined style={{ marginRight: 8 }} />
        {t("pageTitle.scList")}
      </>}
      subtitle={t("pageTitle.scListSubtitle")}
      actions={
        canEdit('special_characteristic') && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/special-characteristics/new")}>
            {t("actions.new")}
          </Button>
        )
      }
    >
      <DataCard title={t("list.title")}>
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            placeholder={t("filter.type")}
            allowClear
            style={{ width: 120 }}
            value={scTypeFilter || undefined}
            onChange={(v) => {
              setScTypeFilter(v || "");
              setPage(1);
            }}
          >
            <Select.Option value="">{t("filter.all")}</Select.Option>
            <Select.Option value="CC">CC</Select.Option>
            <Select.Option value="SC">SC</Select.Option>
          </Select>
          <Select
            placeholder={t("filter.source")}
            allowClear
            style={{ width: 140 }}
            value={sourceTypeFilter || undefined}
            onChange={(v) => {
              setSourceTypeFilter(v || "");
              setPage(1);
            }}
          >
            <Select.Option value="">{t("filter.all")}</Select.Option>
            <Select.Option value="DFMEA">DFMEA</Select.Option>
            <Select.Option value="PFMEA">PFMEA</Select.Option>
          </Select>
          <Switch
            checked={safetyRelatedOnly}
            onChange={(v) => { setSafetyRelatedOnly(v); setPage(1); }}
            checkedChildren={t("filter.safetyRelated")}
            unCheckedChildren={t("filter.all")}
          />
          <Select
            placeholder={t("filter.approvalStatus")}
            allowClear
            style={{ width: 120 }}
            value={approvalStatusFilter || undefined}
            onChange={(v) => { setApprovalStatusFilter(v || ""); setPage(1); }}
          >
            <Select.Option value="">{t("filter.all")}</Select.Option>
            <Select.Option value="pending">{t("approvalStatus.pending")}</Select.Option>
            <Select.Option value="submitted">{t("approvalStatus.submitted")}</Select.Option>
            <Select.Option value="approved">{t("approvalStatus.approved")}</Select.Option>
            <Select.Option value="rejected">{t("approvalStatus.rejected")}</Select.Option>
          </Select>
          <Switch
            checked={suggestedOnly}
            onChange={(v) => { setSuggestedOnly(v); setPage(1); }}
            checkedChildren={t("filter.suggestedOnly")}
            unCheckedChildren={t("filter.all")}
          />
        </Space>

        <Table
          className="qf-table"
          columns={columns}
          dataSource={data}
          rowKey="sc_id"
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
      </DataCard>
    </PageShell>
  );
}
