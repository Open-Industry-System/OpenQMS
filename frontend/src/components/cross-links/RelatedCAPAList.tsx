import { useEffect, useState } from "react";
import { List, Tag, Typography, Empty } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../../api/client";

interface RelatedCAPA {
  report_id: string;
  document_no: string;
  title: string;
  status: string;
  link_sources?: string[];
}

const SOURCE_LABEL_KEY: Record<string, string> = {
  header: "sources.header",
  d4_cause: "sources.d4_cause",
  d7_failure_mode: "sources.d7_failure_mode",
  d7_failure_cause: "sources.d7_failure_cause",
  d7_prevention: "sources.d7_prevention",
};
const SOURCE_ORDER = ["d4_cause", "d7_failure_cause", "d7_failure_mode", "d7_prevention", "header"];

export default function RelatedCAPAList({ fmeaId, fmeaNodeId }: { fmeaId: string; fmeaNodeId?: string }) {
  const navigate = useNavigate();
  const { t } = useTranslation("capa");
  const [items, setItems] = useState<RelatedCAPA[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (fmeaNodeId) params.fmea_node_id = fmeaNodeId;
    client.get(`/capa/by-fmea-node/${fmeaId}`, { params })
      .then((r) => setItems(r.data))
      .finally(() => setLoading(false));
  }, [fmeaId, fmeaNodeId]);

  if (loading) return <List size="small" loading />;
  if (!items.length) {
    return (
      <div data-e2e="related-capa-list">
        <Empty description={t("relatedCapa.empty", "无关联 8D")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }
  const ordered = (srcs: string[] = []) => SOURCE_ORDER.filter((s) => srcs.includes(s));

  return (
    <List
      size="small"
      data-e2e="related-capa-list"
      header={<Typography.Text strong>{t("relatedCapa.title")}</Typography.Text>}
      dataSource={items}
      renderItem={(item) => (
        <List.Item data-e2e="related-capa-item" style={{ cursor: "pointer" }} onClick={() => navigate(`/capa/${item.report_id}`)}>
          <List.Item.Meta title={item.document_no} description={item.title} />
          <span>
            {ordered(item.link_sources).map((s) => (
              <Tag key={s} data-e2e={`related-capa-source-${s}`}>{t(SOURCE_LABEL_KEY[s] || s)}</Tag>
            ))}
          </span>
          <Tag>{item.status}</Tag>
        </List.Item>
      )}
    />
  );
}
