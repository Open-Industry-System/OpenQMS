import { Modal, Button, Space } from "antd";
import { useTranslation } from "react-i18next";

interface AIDraftPreviewProps {
  open: boolean;
  content: string;
  onClose: () => void;
  onReplace: () => void;
  onAppend: () => void;
}

export default function AIDraftPreview({
  open,
  content,
  onClose,
  onReplace,
  onAppend,
}: AIDraftPreviewProps) {
  const { t } = useTranslation("capa");
  const { t: tc } = useTranslation("common");

  return (
    <Modal
      open={open}
      title={t("draft.previewTitle")}
      onCancel={onClose}
      footer={
        <Space>
          <Button onClick={onClose}>{tc("actions.cancel")}</Button>
          <Button onClick={onAppend}>{t("draft.append")}</Button>
          <Button type="primary" onClick={onReplace}>
            {t("draft.replace")}
          </Button>
        </Space>
      }
      width={700}
    >
      <p style={{ color: "#999", marginBottom: 8 }}>
        {t("draft.warning")}
      </p>
      <pre
        style={{
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          background: "#f5f5f5",
          padding: 16,
          borderRadius: 4,
          maxHeight: 400,
          overflow: "auto",
        }}
      >
        {content}
      </pre>
    </Modal>
  );
}
