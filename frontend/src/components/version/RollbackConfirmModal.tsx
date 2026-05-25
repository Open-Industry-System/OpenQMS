import { useState, useEffect } from "react";
import { Modal, Form, Input, Alert, message } from "antd";

interface RollbackConfirmModalProps {
  open: boolean;
  targetVersion: { major_no: number; minor_no: number } | null;
  documentId: string;
  documentType: "fmea" | "cp";
  onClose: () => void;
  onSuccess: () => void;
}

export default function RollbackConfirmModal({
  open,
  targetVersion,
  documentId,
  documentType,
  onClose,
  onSuccess,
}: RollbackConfirmModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      form.resetFields();
    }
  }, [open, form]);

  const handleSubmit = async () => {
    if (!targetVersion) return;

    try {
      const values = await form.validateFields();
      setLoading(true);

      if (documentType === "fmea") {
        const { rollbackFMEAVersion } = await import("../../api/version");
        await rollbackFMEAVersion(
          documentId,
          targetVersion.major_no,
          targetVersion.minor_no,
          { reason: values.reason }
        );
      } else {
        const { rollbackCPVersion } = await import("../../api/version");
        await rollbackCPVersion(
          documentId,
          targetVersion.major_no,
          targetVersion.minor_no,
          { reason: values.reason }
        );
      }

      message.success("版本回退成功");
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      message.error(axiosErr?.response?.data?.detail || "回退失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      title="确认版本回退"
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      destroyOnClose
    >
      <Alert
        message="版本回退说明"
        description={
          <div>
            <p>
              回退到版本 <strong>v{targetVersion?.major_no}.{targetVersion?.minor_no}</strong> 将创建一个新的次版本号，
              内容与目标版本相同。
            </p>
            <p style={{ marginTop: 8, color: "#ff4d4f" }}>
              此操作不可撤销，请谨慎操作。
            </p>
          </div>
        }
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
      />
      <Form form={form} layout="vertical">
        <Form.Item
          name="reason"
          label="回退原因"
          rules={[{ required: true, message: "请输入回退原因" }]}
        >
          <Input.TextArea
            rows={3}
            placeholder="请说明为什么需要回退到此版本..."
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}