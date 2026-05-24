import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Tag, Typography, Card, Form, Input, Select, Switch, App,
  Spin, Row, Col, Descriptions, Space,
} from "antd";
import { ArrowLeftOutlined, SaveOutlined, LinkOutlined } from "@ant-design/icons";
import { getSC, updateSC } from "../../api/specialCharacteristic";
import type { SpecialCharacteristic } from "../../types";
import { useAuthStore } from "../../store/authStore";

const { Title, Text } = Typography;
const { TextArea } = Input;

export default function SCDetailPage() {
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [sc, setSc] = useState<SpecialCharacteristic | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getSC(id)
      .then((data) => {
        setSc(data);
        form.setFieldsValue({
          sc_name: data.sc_name,
          sc_category: data.sc_category,
          spec_requirement: data.spec_requirement,
          customer_symbol: data.customer_symbol,
          sop_ref: data.sop_ref,
          is_supplier_shared: data.is_supplier_shared,
          supplier_code: data.supplier_code,
        });
      })
      .catch(() => message.error("加载特殊特性失败"))
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async (values: Partial<SpecialCharacteristic>) => {
    if (!id) return;
    setSaving(true);
    try {
      const updated = await updateSC(id, values);
      setSc(updated);
      message.success("保存成功");
    } catch {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!sc) {
    return <div>未找到特殊特性</div>;
  }

  const scTypeBg = sc.sc_type === "CC" ? "#fff1f0" : "#fffbe6";

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Space>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate("/special-characteristics")}
          >
            返回列表
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            {sc.sc_code} - {sc.sc_name}
          </Title>
          <Tag color={sc.sc_type === "CC" ? "red" : "gold"}>
            {sc.sc_type}
          </Tag>
        </Space>
      </div>

      <Row gutter={16}>
        {/* Left: Read-only info */}
        <Col span={10}>
          <Card title="基本信息" style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="SC编号">
                {sc.sc_code}
              </Descriptions.Item>
              <Descriptions.Item label="类型">
                <span
                  style={{
                    backgroundColor: scTypeBg,
                    padding: "2px 8px",
                    borderRadius: 4,
                  }}
                >
                  <Tag color={sc.sc_type === "CC" ? "red" : "gold"}>
                    {sc.sc_type === "CC" ? "关键特性 (CC)" : "重要特性 (SC)"}
                  </Tag>
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="产品线">
                {sc.product_line_code}
              </Descriptions.Item>
              <Descriptions.Item label="来源类型">
                <Tag color={sc.source_type === "DFMEA" ? "blue" : "green"}>
                  {sc.source_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="来源FMEA文档">
                {sc.source_fmea_document_no ? (
                  <Button
                    type="link"
                    size="small"
                    icon={<LinkOutlined />}
                    onClick={() => navigate(`/fmea/${sc.source_fmea_id}`)}
                  >
                    {sc.source_fmea_document_no}
                  </Button>
                ) : (
                  "-"
                )}
              </Descriptions.Item>
              <Descriptions.Item label="来源节点ID">
                <Text copyable>{sc.source_node_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="父级特性">
                {sc.parent_sc_id ? (
                  <Button
                    type="link"
                    size="small"
                    onClick={() =>
                      navigate(`/special-characteristics/${sc.parent_sc_id}`)
                    }
                  >
                    {sc.parent_sc_id}
                  </Button>
                ) : (
                  "-"
                )}
              </Descriptions.Item>
              <Descriptions.Item label="MSA状态">
                <Tag
                  color={
                    sc.msa_status === "PASS"
                      ? "green"
                      : sc.msa_status === "FAIL"
                      ? "red"
                      : "orange"
                  }
                >
                  {sc.msa_status}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* Source FMEA info */}
          {sc.source_fmea_title && (
            <Card title="来源FMEA信息">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="FMEA标题">
                  {sc.source_fmea_title}
                </Descriptions.Item>
                <Descriptions.Item label="文档编号">
                  {sc.source_fmea_document_no}
                </Descriptions.Item>
                <Descriptions.Item label="查看FMEA">
                  <Button
                    type="primary"
                    size="small"
                    onClick={() => navigate(`/fmea/${sc.source_fmea_id}`)}
                  >
                    打开FMEA编辑器
                  </Button>
                </Descriptions.Item>
              </Descriptions>
            </Card>
          )}
        </Col>

        {/* Right: Editable form */}
        <Col span={14}>
          <Card title="编辑信息">
            <Form
              form={form}
              layout="vertical"
              onFinish={handleSave}
              disabled={isViewer}
            >
              <Form.Item
                name="sc_name"
                label="特性名称"
                rules={[{ required: true, message: "请输入特性名称" }]}
              >
                <Input placeholder="请输入特性名称" />
              </Form.Item>

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="sc_category" label="特性分类">
                    <Select placeholder="请选择" allowClear>
                      <Select.Option value="产品特性">
                        产品特性
                      </Select.Option>
                      <Select.Option value="过程特性">
                        过程特性
                      </Select.Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="customer_symbol" label="客户符号">
                    <Input placeholder="客户特殊符号标识" />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item name="spec_requirement" label="规格要求">
                <TextArea rows={4} placeholder="请输入规格要求" />
              </Form.Item>

              <Form.Item name="sop_ref" label="SOP参考">
                <Input placeholder="SOP文档编号" />
              </Form.Item>

              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item
                    name="is_supplier_shared"
                    label="供应商共享"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                </Col>
                <Col span={16}>
                  <Form.Item name="supplier_code" label="供应商代码">
                    <Input placeholder="供应商代码" />
                  </Form.Item>
                </Col>
              </Row>

              {!isViewer && (
                <Form.Item>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<SaveOutlined />}
                    loading={saving}
                  >
                    保存
                  </Button>
                </Form.Item>
              )}
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
