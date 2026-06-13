import { useState, useEffect } from "react";
import { Modal, Form, Input, Switch, message } from "antd";

interface CreateVersionModalProps {
  open: boolean;
  documentId: string;
  documentType: "fmea" | "cp";
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateVersionModal({
  open,
  documentId,
  documentType,
  onClose,
  onSuccess,
}: CreateVersionModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      form.resetFields();
    }
  }, [open, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      if (documentType === "fmea") {
        const { createFMEAVersion } = await import("../../api/version");
        await createFMEAVersion(documentId, {
          change_summary: values.change_summary,
          is_major: values.is_major || false,
        });
      } else {
        const { createCPVersion } = await import("../../api/version");
        await createCPVersion(documentId, {
          change_summary: values.change_summary,
          is_major: values.is_major || false,
        });
      }

      message.success("版本创建成功");
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "创建失败";
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      title="创建版本"
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="change_summary"
          label="变更摘要"
          rules={[{ required: true, message: "请输入变更摘要" }]}
        >
          <Input.TextArea
            rows={4}
            placeholder="请描述本次版本变更的主要内容..."
          />
        </Form.Item>
        <Form.Item name="is_major" label="主版本" valuePropName="checked">
          <Switch checkedChildren="主" unCheckedChildren="次" />
        </Form.Item>
      </Form>
    </Modal>
  );
}