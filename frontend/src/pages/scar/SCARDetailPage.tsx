import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Tag, Button, Space, Descriptions, Input, Modal, message, Spin, Row, Col } from "antd";
import { getSCAR, transitionSCAR, linkCAPA } from "../../api/scar";
import { createCAPA, getCAPA } from "../../api/capa";
import { STATUS_COLORS, STATUS_LABELS, SOURCE_LABELS } from "./SCARListPage";
import type { SupplierSCAR, CAPAReport } from "../../types";

export default function SCARDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [scar, setScar] = useState<SupplierSCAR | null>(null);
  const [loading, setLoading] = useState(true);
  const [respondModalOpen, setRespondModalOpen] = useState(false);
  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [capaModalOpen, setCapaModalOpen] = useState(false);
  const [responseText, setResponseText] = useState("");
  const [resolutionText, setResolutionText] = useState("");
  const [capaInfo, setCapaInfo] = useState<{ document_no: string; status: string } | null>(null);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getSCAR(id);
      setScar(data);
      if (data.capa_ref_id) {
        try {
          const capa = await getCAPA(data.capa_ref_id);
          setCapaInfo({ document_no: capa.document_no, status: capa.status });
        } catch {
          setCapaInfo(null);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const doTransition = async (action: string, extra?: Record<string, string>) => {
    if (!id) return;
    await transitionSCAR(id, { action, ...extra } as Parameters<typeof transitionSCAR>[1]);
    message.success("状态更新成功");
    load();
  };

  const handleRespond = async () => {
    if (!responseText.trim()) { message.warning("请输入供应商回复"); return; }
    await doTransition("respond", { supplier_response: responseText });
    setRespondModalOpen(false);
    setResponseText("");
  };

  const handleClose = async () => {
    if (!resolutionText.trim()) { message.warning("请输入解决摘要"); return; }
    await doTransition("close", { resolution_summary: resolutionText });
    setCloseModalOpen(false);
    setResolutionText("");
  };

  const handleCreateCAPA = async () => {
    if (!id || !scar) return;
    const now = new Date();
    const seq = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
    const capa = await createCAPA({
      title: `${scar.scar_no} — ${scar.description.slice(0, 50)}`,
      document_no: `8D-${seq}`,
      severity: "一般",
      due_date: scar.due_date || undefined,
      product_line_code: scar.product_line_code || "DC-DC-100",
    });
    await linkCAPA(id, { capa_ref_id: capa.report_id });
    message.success("CAPA 创建并关联成功");
    setCapaModalOpen(false);
    load();
  };

  if (loading || !scar) {
    return <div style={{ textAlign: "center", padding: 100 }}><Spin size="large" /></div>;
  }

  const actionButtons = () => {
    const btns: ReactNode[] = [];
    if (scar.status === "open") {
      btns.push(<Button key="start" type="primary" onClick={() => doTransition("start")}>开始处理</Button>);
    }
    if (scar.status === "in_progress") {
      btns.push(<Button key="respond" type="primary" onClick={() => setRespondModalOpen(true)}>提交回复</Button>);
    }
    if (scar.status === "responded") {
      btns.push(<Button key="verify" type="primary" onClick={() => doTransition("verify")}>验证通过</Button>);
      btns.push(<Button key="reject" danger onClick={() => doTransition("reject")}>退回</Button>);
    }
    if (scar.status === "verified") {
      btns.push(<Button key="close" type="primary" onClick={() => setCloseModalOpen(true)}>关闭</Button>);
      btns.push(<Button key="reopen" onClick={() => doTransition("reopen")}>重新打开</Button>);
    }
    return btns;
  };

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <span style={{ fontSize: 20, fontWeight: 600 }}>{scar.scar_no}</span>
              <Tag color={STATUS_COLORS[scar.status]}>{STATUS_LABELS[scar.status]}</Tag>
            </Space>
          </Col>
          <Col>
            <Space>{actionButtons()}</Space>
          </Col>
        </Row>
      </Card>

      <Card title="SCAR 信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="供应商">{scar.supplier_name || scar.supplier_id}</Descriptions.Item>
          <Descriptions.Item label="来源">{SOURCE_LABELS[scar.source_type] || scar.source_type}</Descriptions.Item>
          <Descriptions.Item label="产品线">{scar.product_line_code || "-"}</Descriptions.Item>
          <Descriptions.Item label="发出日期">{scar.issued_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="到期日">{scar.due_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="关闭日期">{scar.closed_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="问题描述" span={2}>{scar.description}</Descriptions.Item>
          <Descriptions.Item label="要求措施" span={2}>{scar.requested_action || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="供应商回复" style={{ marginBottom: 16 }}>
        {scar.supplier_response ? (
          <div style={{ whiteSpace: "pre-wrap" }}>{scar.supplier_response}</div>
        ) : (
          <div style={{ color: "#999" }}>暂无回复</div>
        )}
      </Card>

      <Card title="CAPA 关联" style={{ marginBottom: 16 }}>
        {scar.capa_ref_id && capaInfo ? (
          <Space>
            <span>已关联 8D: <strong>{capaInfo.document_no}</strong></span>
            <Tag>{capaInfo.status}</Tag>
            <Button type="link" onClick={() => navigate(`/capa/${scar.capa_ref_id}`)}>查看</Button>
          </Space>
        ) : (
          <Button type="dashed" onClick={() => setCapaModalOpen(true)}>创建关联 8D</Button>
        )}
      </Card>

      {scar.resolution_summary && (
        <Card title="解决摘要">
          <div style={{ whiteSpace: "pre-wrap" }}>{scar.resolution_summary}</div>
        </Card>
      )}

      {/* Respond Modal */}
      <Modal title="提交供应商回复" open={respondModalOpen} onCancel={() => setRespondModalOpen(false)} onOk={handleRespond}>
        <Input.TextArea rows={4} value={responseText} onChange={(e) => setResponseText(e.target.value)} placeholder="请输入供应商回复内容" />
      </Modal>

      {/* Close Modal */}
      <Modal title="关闭 SCAR" open={closeModalOpen} onCancel={() => setCloseModalOpen(false)} onOk={handleClose}>
        <Input.TextArea rows={4} value={resolutionText} onChange={(e) => setResolutionText(e.target.value)} placeholder="请输入解决摘要" />
      </Modal>

      {/* Create CAPA Modal */}
      <Modal title="创建关联 8D" open={capaModalOpen} onCancel={() => setCapaModalOpen(false)} onOk={handleCreateCAPA} confirmLoading={false}>
        <p>将基于 SCAR 信息创建新的 8D/CAPA 记录并自动关联。</p>
        <p>SCAR: {scar.scar_no}</p>
        <p>描述: {scar.description.slice(0, 100)}...</p>
      </Modal>
    </div>
  );
}
