import { Card, List, Tag, Typography } from "antd";
import type { QAResponse } from "../../api/search";

const { Paragraph, Text } = Typography;

interface Props {
  data: QAResponse;
}

export default function QAAnswer({ data }: Props) {
  return (
    <div>
      <Card title="💬 回答" style={{ marginBottom: 16 }}>
        <Paragraph style={{ whiteSpace: "pre-wrap" }}>{data.answer}</Paragraph>
      </Card>

      {data.sources.length > 0 && (
        <Card title={`引用来源 (${data.sources.length})`} size="small">
          <List
            dataSource={data.sources}
            renderItem={(item, index) => (
              <List.Item>
                <Text>
                  [{index + 1}]{" "}
                  <Tag color={item.entity_type === "fmea_node" ? "blue" : "orange"}>
                    {item.entity_type}
                  </Tag>
                  <Text strong>{item.document_no}</Text>
                  {" — "}
                  {item.chunk_text.length > 100
                    ? item.chunk_text.slice(0, 100) + "..."
                    : item.chunk_text}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    相关度: {(item.relevance_score * 100).toFixed(0)}%
                  </Text>
                </Text>
              </List.Item>
            )}
          />
        </Card>
      )}

      <div style={{ marginTop: 8 }}>
        <Text type="secondary">
          查询耗时: {data.query_time_ms}ms | LLM: {data.llm_available ? "✅" : "❌"}
        </Text>
      </div>
    </div>
  );
}
