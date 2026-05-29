import React, { useState } from "react";
import { Modal, Upload, Button, Table, message, Space, Typography } from "antd";
import { InboxOutlined, DownloadOutlined } from "@ant-design/icons";
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
  title = "批量导入",
}: ImportExcelDialogProps) {
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
        message.success(`成功导入 ${result.imported_count} 条记录`);
        onImported(result.imported_count);
        handleClose();
      }
    } catch {
      message.error("导入失败，请检查文件格式");
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
    { title: "行号", dataIndex: "row", key: "row", width: 80 },
    { title: "字段", dataIndex: "field", key: "field", width: 120 },
    { title: "错误信息", dataIndex: "message", key: "message" },
  ];

  return (
    <Modal
      title={title}
      open={open}
      onCancel={handleClose}
      footer={null}
      width={600}
      destroyOnClose
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
            <Button onClick={() => { setErrors([]); setFileList([]); }}>重新选择文件</Button>
            <Button onClick={handleClose}>取消</Button>
          </Space>
        </>
      ) : (
        <>
          <Dragger
            accept=".xlsx"
            fileList={fileList}
            beforeUpload={(file) => {
              if (file.size > 10 * 1024 * 1024) {
                message.error("文件超过 10MB 限制");
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
            <p className="ant-upload-text">点击或拖拽 .xlsx 文件到此区域上传</p>
            {hint && <p className="ant-upload-hint">{hint}</p>}
          </Dragger>
          <div style={{ marginTop: 12, textAlign: "center" }}>
            <Link onClick={handleDownloadTemplate}>
              <DownloadOutlined /> 下载导入模板
            </Link>
          </div>
        </>
      )}
    </Modal>
  );
}
