import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tag, Typography, Space, App, Card, Row, Col, Statistic, Button } from "antd";
import { ApartmentOutlined, CheckCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getMatrix } from "../../../api/specialCharacteristic";
import type { MatrixRow } from "../../../types";
import { useProductLineStore } from "../../../store/productLineStore";

const { Title } = Typography;

const msaStatusColors: Record<string, string> = {
  PASS: "green",
  FAIL: "red",
  PENDING: "orange",
};

export default function SCMatrixPage() {
  const { t } = useTranslation("specialCharacteristic");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [data, setData] = useState<MatrixRow[]>([]);
  const [loading, setLoading] = useState(true);
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = () => {
    setLoading(true);
    getMatrix(productLine || undefined)
      .then((res) => setData(res.characteristics))
      .catch(() => message.error(t("message.loadFailed")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  // Coverage stats
  const total = data.length;
  const dfmeaCount = data.filter((d) => d.has_dfmea).length;
  const pfmeaCount = data.filter((d) => d.has_pfmea).length;
  const cpCount = data.filter((d) => d.has_cp).length;
  const msaPassCount = data.filter((d) => d.msa_status === "PASS").length;
  const sopCount = data.filter((d) => d.has_sop).length;

  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);

  const renderLinkCell = (
    has: boolean,
    link: string | null,
    label: string
  ) => {
    if (!has) {
      return <span style={{ color: "#bbb" }}>-</span>;
    }
    if (link) {
      return (
        <Tag
          color="green"
          style={{ cursor: "pointer" }}
          onClick={() => navigate(link)}
        >
          {label}
        </Tag>
      );
    }
    return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
  };

  const columns = [
    {
      title: t("column.scCode"),
      dataIndex: "sc_code",
      key: "sc_code",
      width: 130,
      render: (code: string, record: MatrixRow) => (
        <Button
          type="link"
          size="small"
          onClick={() => navigate(`/special-characteristics/${record.sc_id}`)}
          style={{
            backgroundColor: record.is_safety_related ? "#fff2f0" : undefined,
            padding: "2px 8px",
            borderRadius: 4,
          }}
        >
          {code}
        </Button>
      ),
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
      width: 80,
      render: (t: string, record: MatrixRow) => (
        <Tag
          color={t === "CC" ? "red" : "gold"}
          style={{ backgroundColor: record.is_safety_related ? "#fff2f0" : undefined }}
        >
          {t}
        </Tag>
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
      title: t("matrixColumn.dfmea"),
      dataIndex: "has_dfmea",
      key: "dfmea",
      width: 90,
      align: "center" as const,
      render: (_: boolean, record: MatrixRow) =>
        renderLinkCell(record.has_dfmea, record.dfmea_link, t("matrixColumn.dfmea")),
    },
    {
      title: t("matrixColumn.pfmea"),
      dataIndex: "has_pfmea",
      key: "pfmea",
      width: 90,
      align: "center" as const,
      render: (_: boolean, record: MatrixRow) =>
        renderLinkCell(record.has_pfmea, record.pfmea_link, t("matrixColumn.pfmea")),
    },
    {
      title: t("matrixColumn.cp"),
      dataIndex: "has_cp",
      key: "cp",
      width: 70,
      align: "center" as const,
      render: (_: boolean, record: MatrixRow) =>
        renderLinkCell(record.has_cp, record.cp_link, t("matrixColumn.cp")),
    },
    {
      title: t("matrixColumn.msa"),
      dataIndex: "msa_status",
      key: "msa",
      width: 100,
      align: "center" as const,
      render: (status: string, record: MatrixRow) => {
        if (status === "PASS" && record.msa_link) {
          return (
            <Tag
              color="green"
              style={{ cursor: "pointer" }}
              onClick={() => navigate(record.msa_link!)}
            >
              PASS
            </Tag>
          );
        }
        return (
          <Tag color={msaStatusColors[status] || "default"}>
            {status}
          </Tag>
        );
      },
    },
    {
      title: t("matrixColumn.sop"),
      dataIndex: "has_sop",
      key: "sop",
      width: 70,
      align: "center" as const,
      render: (_: boolean, record: MatrixRow) =>
        record.has_sop ? (
          <CheckCircleOutlined style={{ color: "#52c41a" }} />
        ) : (
          <span style={{ color: "#bbb" }}>-</span>
        ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Space>
          <Title level={4} style={{ margin: 0 }}>
            <ApartmentOutlined style={{ marginRight: 8 }} />
            {t("pageTitle.scMatrix")}
          </Title>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="sc_id"
        loading={loading}
        pagination={false}
        size="middle"
        scroll={{ x: 900 }}
      />

      <Card style={{ marginTop: 16 }}>
        <Title level={5} style={{ marginBottom: 16 }}>
          {t("matrix.coverageStats")}
        </Title>
        <Row gutter={16}>
          <Col span={4}>
            <Statistic title={t("matrix.total")} value={total} />
          </Col>
          <Col span={4}>
            <Statistic
              title={t("matrix.dfmeaCoverage")}
              value={pct(dfmeaCount)}
              suffix="%"
              valueStyle={{
                color: dfmeaCount === total ? "#52c41a" : undefined,
              }}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title={t("matrix.pfmeaCoverage")}
              value={pct(pfmeaCount)}
              suffix="%"
              valueStyle={{
                color: pfmeaCount === total ? "#52c41a" : undefined,
              }}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title={t("matrix.cpCoverage")}
              value={pct(cpCount)}
              suffix="%"
              valueStyle={{
                color: cpCount === total ? "#52c41a" : undefined,
              }}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title={t("matrix.msaPass")}
              value={pct(msaPassCount)}
              suffix="%"
              valueStyle={{
                color: msaPassCount === total ? "#52c41a" : undefined,
              }}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title={t("matrix.sopCoverage")}
              value={pct(sopCount)}
              suffix="%"
              valueStyle={{
                color: sopCount === total ? "#52c41a" : undefined,
              }}
            />
          </Col>
        </Row>
      </Card>
    </div>
  );
}
