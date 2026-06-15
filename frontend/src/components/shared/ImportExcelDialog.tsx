import React, { useState } from "react";
import { Modal, Upload, Button, Table, message, Space, Typography } from "antd";
import { InboxOutlined, DownloadOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { UploadFile } from "antd/es/upload";
import type { ImportResult, ImportRowError } from "../../utils/excel";

const { Dragger } = Upload;
const { Link } = Typography;

interface ImportExcelDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: (count: number) => void;
  importFn: (file: File) => Promise<ImportResult>;
  templateDownloadFn?: () => Promise<void>;
  hint?: string;
  title?: string;
}

export default function ImportExcelDialog({
  open,
  onClose,
  onImported,
  importFn,
  templateDownloadFn,
  hint,
  title,
}: ImportExcelDialogProps) {
  const { t } = useTranslation("shared");
  const { t: tc } = useTranslation("common");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<ImportRowError[]>([]);
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const handleUpload = async (file: File) => {
    setLoading(true);
    setErrors([]);
    try {
      const result: ImportResult = await importFn(file);
      if (result.errors && result.errors.length > 0) {
        setErrors(result.errors);
      } else {
        message.success(t("import.success", { count: result.imported_count }));
        onImported(result.imported_count);
        handleClose();
      }
    } catch {
      message.error(t("import.failed"));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setErrors([]);
    setFileList([]);
    onClose();
  };

  const handleDownloadTemplate = async () => {
    if (templateDownloadFn) {
      await templateDownloadFn();
    }
  };

  const errorColumns = [
    { title: t("import.columns.row"), dataIndex: "row", key: "row", width: 80 },
    { title: t("import.columns.field"), dataIndex: "field", key: "field", width: 120 },
    { title: t("import.columns.message"), dataIndex: "message", key: "message" },
  ];

  return (
    <Modal
      title={title || t("import.title")}
      open={open}
      onCancel={handleClose}
      footer={null}
      width={600}
      destroyOnHidden
    >
      {errors.length > 0 ? (
        <>
          <Table
            dataSource={errors.map((e, i) => ({ ...e, key: i }))}
            columns={errorColumns}
            size="small"
            pagination={{ pageSize: 10 }}
            style={{ marginBottom: 16 }}
          />
          <Space>
            <Button onClick={() => { setErrors([]); setFileList([]); }}>{t("import.reselect")}</Button>
            <Button onClick={handleClose}>{tc("actions.cancel")}</Button>
          </Space>
        </>
      ) : (
        <>
          <Dragger
            accept=".xlsx"
            fileList={fileList}
            beforeUpload={(file) => {
              if (file.size > 10 * 1024 * 1024) {
                message.error(t("import.fileTooLarge"));
                return Upload.LIST_IGNORE;
              }
              handleUpload(file);
              return false;
            }}
            onChange={({ fileList: newList }) => setFileList(newList)}
            disabled={loading}
            maxCount={1}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">{t("import.dragText")}</p>
            {hint && <p className="ant-upload-hint">{hint}</p>}
          </Dragger>
          <div style={{ marginTop: 12, textAlign: "center" }}>
            <Link onClick={handleDownloadTemplate}>
              <DownloadOutlined /> {t("import.downloadTemplate")}
            </Link>
          </div>
        </>
      )}
    </Modal>
  );
}
