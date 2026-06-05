import { Modal, Button, Space } from "antd";

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
  return (
    <Modal
      open={open}
      title="AI 草稿预览"
      onCancel={onClose}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button onClick={onAppend}>追加</Button>
          <Button type="primary" onClick={onReplace}>
            替换
          </Button>
        </Space>
      }
      width={700}
    >
      <p style={{ color: "#999", marginBottom: 8 }}>
        此为 AI 生成的草稿，请审核后再使用
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
