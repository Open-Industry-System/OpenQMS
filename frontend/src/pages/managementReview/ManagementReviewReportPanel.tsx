import { useState, useEffect } from "react";
import { Card, Button, Space, Tag, Collapse, Spin, message, Modal, Empty, Alert } from "antd";
import {
  generateReport, saveReportDraft, finalizeReport, reopenReport,
  listReportVersions, exportReport,
} from "../../api/managementReview";
import { usePermission } from "../../hooks/usePermission";
import type {
  ManagementReview,
  ManagementReviewReport,
  ManagementReviewReportSection,
  ReviewReportVersion,
} from "../../types";
import ReportSectionEditor from "./ReportSectionEditor";
import ReportVersionList from "./ReportVersionList";

interface Props {
  review: ManagementReview;
  onReviewChange: (review: ManagementReview) => void;
}

const statusMap: Record<string, { color: string; label: string }> = {
  none: { color: "default", label: "未生成" },
  draft: { color: "blue", label: "草稿" },
  final: { color: "green", label: "已定稿" },
};

export default function ManagementReviewReportPanel({ review, onReviewChange }: Props) {
  const { canCreate, canApprove } = usePermission();
  const [report, setReport] = useState<ManagementReviewReport | null>(review.generated_report);
  const [versions, setVersions] = useState<ReviewReportVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [previewVersion, setPreviewVersion] = useState<ReviewReportVersion | null>(null);
  const readOnly = review.status === "closed" || review.report_status === "final";

  // Only rehydrate report data when switching reviews, not on every parent re-render
  useEffect(() => {
    setReport(review.generated_report);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review.review_id]);

  // Load versions on review change (history may exist even after reopen to draft)
  useEffect(() => {
    loadVersions();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review.review_id]);

  const loadVersions = async () => {
    const data = await listReportVersions(review.review_id);
    setVersions(data);
  };

  const handleGenerate = async () => {
    if (review.report_status === "draft" && report) {
      Modal.confirm({
        title: "确认重新生成？",
        content: "重新生成将覆盖当前草稿中的人工编辑内容。",
        onOk: async () => {
          await doGenerate();
        },
      });
      return;
    }
    await doGenerate();
  };

  const doGenerate = async () => {
    setLoading(true);
    try {
      const data = await generateReport(review.review_id);
      setReport(data.generated_report);
      onReviewChange({ ...review, report_status: data.report_status, generated_report: data.generated_report });
      message.success("报告生成成功");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!report) return;
    try {
      const data = await saveReportDraft(review.review_id, report);
      setReport(data.generated_report);
      onReviewChange({ ...review, report_status: data.report_status, generated_report: data.generated_report });
      message.success("草稿已保存");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "保存失败");
    }
  };

  const handleFinalize = async () => {
    try {
      const version = await finalizeReport(review.review_id);
      setVersions((prev) => [version, ...prev]);
      onReviewChange({ ...review, report_status: "final" });
      message.success("报告已定稿归档");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "定稿失败");
    }
  };

  const handleReopen = async () => {
    try {
      const data = await reopenReport(review.review_id);
      onReviewChange({ ...review, report_status: data.report_status });
      message.success("报告已重新打开");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "重新打开失败");
    }
  };

  const handleExport = async () => {
    try {
      const data = await exportReport(review.review_id);
      const blob = new Blob([data.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${review.doc_no}-${review.title}-报告.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(e.response?.data?.detail || "导出失败");
    }
  };

  const updateSection = (index: number, section: ManagementReviewReportSection) => {
    if (!report) return;
    const sections = [...report.sections];
    sections[index] = section;
    setReport({ ...report, sections });
  };

  const collapseItems = report?.sections.map((section, index) => ({
    key: section.key,
    label: section.title,
    children: (
      <ReportSectionEditor
        section={section}
        readOnly={readOnly}
        onChange={(s) => updateSection(index, s)}
      />
    ),
  })) || [];

  const handleRestorePreview = () => {
    if (!previewVersion) return;
    Modal.confirm({
      title: "恢复为草稿？",
      content: `将历史版本 v${previewVersion.version_no} 的内容恢复为当前草稿，当前草稿内容将被覆盖。`,
      onOk: () => {
        setReport(previewVersion.content);
        setPreviewVersion(null);
        message.success("已恢复为草稿");
      },
    });
  };

  return (
    <Card title="管理评审报告">
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space>
          <span>报告状态：<Tag color={statusMap[review.report_status]?.color}>{statusMap[review.report_status]?.label}</Tag></span>
          {!readOnly && canCreate("management_review") && (
            <Button type="primary" onClick={handleGenerate} loading={loading}>
              {report ? "重新生成" : "AI 生成报告"}
            </Button>
          )}
          {!readOnly && canCreate("management_review") && report && (
            <Button onClick={handleSave}>保存草稿</Button>
          )}
          {review.report_status === "draft" && canApprove("management_review") && report && (
            <Button type="primary" danger onClick={handleFinalize}>定稿归档</Button>
          )}
          {review.report_status === "final" && canApprove("management_review") && review.status !== "closed" && (
            <Button onClick={handleReopen}>重新打开编辑</Button>
          )}
          {report && <Button onClick={handleExport}>导出 Markdown</Button>}
        </Space>

        <div style={{ display: "flex", gap: 16 }}>
          <div style={{ flex: 1 }}>
            {previewVersion ? (
              <Spin spinning={loading}>
                <Alert
                  message={`正在预览历史版本 v${previewVersion.version_no}`}
                  type="info"
                  showIcon
                  action={
                    <Space>
                      {!readOnly && canCreate("management_review") && (
                        <Button size="small" onClick={handleRestorePreview}>恢复为草稿</Button>
                      )}
                      <Button size="small" onClick={() => setPreviewVersion(null)}>取消预览</Button>
                    </Space>
                  }
                  style={{ marginBottom: 12 }}
                />
                <Collapse items={previewVersion.content.sections.map((section, _index) => ({
                  key: section.key,
                  label: section.title,
                  children: (
                    <ReportSectionEditor
                      section={section}
                      readOnly={true}
                      onChange={() => {}}
                    />
                  ),
                }))} />
              </Spin>
            ) : report ? (
              <Spin spinning={loading}>
                <Collapse items={collapseItems} />
              </Spin>
            ) : (
              <Empty description="暂无报告数据，请点击「AI 生成报告」开始初始化" />
            )}
          </div>
          {versions.length > 0 && (
            <div style={{ width: 240 }}>
              <Card title="历史版本" size="small">
                <ReportVersionList
                  versions={versions}
                  onSelect={(v) => setPreviewVersion(v)}
                />
              </Card>
            </div>
          )}
        </div>
      </Space>
    </Card>
  );
}
