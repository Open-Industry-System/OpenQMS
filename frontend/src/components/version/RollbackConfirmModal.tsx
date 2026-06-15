import { useState, useEffect } from "react";
import { Modal, Form, Input, Alert, message } from "antd";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation("version");
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

      message.success(t("rollback.success"));
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      message.error(axiosErr?.response?.data?.detail || t("rollback.failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("rollback.title")}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Alert
        message={t("rollback.descriptionTitle")}
        description={
          <div>
            <p>
              {t("rollback.description", { major: targetVersion?.major_no, minor: targetVersion?.minor_no })}
            </p>
            <p style={{ marginTop: 8, color: "#ff4d4f" }}>
              {t("rollback.irreversible")}
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
          label={t("rollback.reasonLabel")}
          rules={[{ required: true, message: t("rollback.reasonRequired") }]}
        >
          <Input.TextArea
            rows={3}
            placeholder={t("rollback.reasonPlaceholder")}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
