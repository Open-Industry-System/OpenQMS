import { useEffect, useState } from "react";
import { List, Tag, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

interface RelatedCAPA {
  report_id: string;
  document_no: string;
  title: string;
  status: string;
}

export default function RelatedCAPAList({
  fmeaId,
  fmeaNodeId,
}: {
  fmeaId: string;
  fmeaNodeId?: string;
}) {
  const navigate = useNavigate();
  const [items, setItems] = useState<RelatedCAPA[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (fmeaNodeId) params.fmea_node_id = fmeaNodeId;
    client
      .get(`/capa/by-fmea-node/${fmeaId}`, { params })
      .then((r) => setItems(r.data))
      .finally(() => setLoading(false));
  }, [fmeaId, fmeaNodeId]);

  if (!items.length && !loading) return null;

  return (
    <List
      size="small"
      header={<Typography.Text strong>关联 CAPA</Typography.Text>}
      loading={loading}
      dataSource={items}
      renderItem={(item) => (
        <List.Item
          style={{ cursor: "pointer" }}
          onClick={() => navigate(`/capa/${item.report_id}`)}
        >
          <List.Item.Meta
            title={item.document_no}
            description={item.title}
          />
          <Tag>{item.status}</Tag>
        </List.Item>
      )}
    />
  );
}
