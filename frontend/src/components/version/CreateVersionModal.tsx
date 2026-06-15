import { useState, useEffect } from "react";
import { Modal, Form, Input, Switch, message } from "antd";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation("version");
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

      message.success(t("create.success"));
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : t("create.failed");
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("create.title")}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="change_summary"
          label={t("create.summaryLabel")}
          rules={[{ required: true, message: t("create.summaryRequired") }]}
        >
          <Input.TextArea
            rows={4}
            placeholder={t("create.summaryPlaceholder")}
          />
        </Form.Item>
        <Form.Item name="is_major" label={t("create.isMajor")} valuePropName="checked">
          <Switch checkedChildren={t("create.major")} unCheckedChildren={t("create.minor")} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
