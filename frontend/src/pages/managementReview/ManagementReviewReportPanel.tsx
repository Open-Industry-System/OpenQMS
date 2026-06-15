import { useState, useEffect } from "react";
import { Card, Button, Space, Tag, Collapse, Spin, message, Modal, Empty, Alert } from "antd";
import { useTranslation } from "react-i18next";
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
import { useReportStatusMap, useReportStatusColor } from "./useOptions";

interface Props {
  review: ManagementReview;
  onReviewChange: (review: ManagementReview) => void;
}

export default function ManagementReviewReportPanel({ review, onReviewChange }: Props) {
  const { t } = useTranslation("managementReview");
  const { canCreate, canApprove } = usePermission();
  const reportStatusMap = useReportStatusMap();
  const reportStatusColor = useReportStatusColor();

  const [report, setReport] = useState<ManagementReviewReport | null>(review.generated_report);
  const [versions, setVersions] = useState<ReviewReportVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [previewVersion, setPreviewVersion] = useState<ReviewReportVersion | null>(null);
  const readOnly = review.status === "closed" || review.report_status === "final";

  useEffect(() => {
    setReport(review.generated_report);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review.review_id]);

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
        title: t("report.regenerateConfirmTitle"),
        content: t("report.regenerateConfirmContent"),
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
      message.success(t("messages.operationSuccess"));
    } catch (e: any) {
      message.error(e.response?.data?.detail || t("messages.generateFailed"));
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
      message.success(t("messages.saveDraftSuccess"));
    } catch (e: any) {
      message.error(e.response?.data?.detail || t("messages.saveDraftFailed"));
    }
  };

  const handleFinalize = async () => {
    try {
      const version = await finalizeReport(review.review_id);
      setVersions((prev) => [version, ...prev]);
      onReviewChange({ ...review, report_status: "final" });
      message.success(t("messages.finalizeSuccess"));
    } catch (e: any) {
      message.error(e.response?.data?.detail || t("messages.finalizeFailed"));
    }
  };

  const handleReopen = async () => {
    try {
      const data = await reopenReport(review.review_id);
      onReviewChange({ ...review, report_status: data.report_status });
      message.success(t("messages.reopenSuccess"));
    } catch (e: any) {
      message.error(e.response?.data?.detail || t("messages.reopenFailed"));
    }
  };

  const handleExport = async () => {
    try {
      const data = await exportReport(review.review_id);
      const blob = new Blob([data.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${review.doc_no}-report.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(e.response?.data?.detail || t("messages.exportFailed"));
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
      title: t("report.restoreConfirmTitle"),
      content: t("report.restoreConfirmContent", { version: previewVersion.version_no }),
      onOk: () => {
        setReport(previewVersion.content);
        setPreviewVersion(null);
        message.success(t("messages.restoreSuccess"));
      },
    });
  };

  return (
    <Card title={t("card.report")}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space>
          <span>{t("report.statusLabel")}<Tag color={reportStatusColor[review.report_status]}>{reportStatusMap[review.report_status]}</Tag></span>
          {!readOnly && canCreate("management_review") && (
            <Button type="primary" onClick={handleGenerate} loading={loading}>
              {report ? t("actions.regenerate") : t("actions.generateReport")}
            </Button>
          )}
          {!readOnly && canCreate("management_review") && report && (
            <Button onClick={handleSave}>{t("actions.saveDraft")}</Button>
          )}
          {review.report_status === "draft" && canApprove("management_review") && report && (
            <Button type="primary" danger onClick={handleFinalize}>{t("actions.finalize")}</Button>
          )}
          {review.report_status === "final" && canApprove("management_review") && review.status !== "closed" && (
            <Button onClick={handleReopen}>{t("actions.reopenEdit")}</Button>
          )}
          {report && <Button onClick={handleExport}>{t("actions.exportMarkdown")}</Button>}
        </Space>

        <div style={{ display: "flex", gap: 16 }}>
          <div style={{ flex: 1 }}>
            {previewVersion ? (
              <Spin spinning={loading}>
                <Alert
                  message={t("report.previewingVersion", { version: previewVersion.version_no })}
                  type="info"
                  showIcon
                  action={
                    <Space>
                      {!readOnly && canCreate("management_review") && (
                        <Button size="small" onClick={handleRestorePreview}>{t("actions.restoreDraft")}</Button>
                      )}
                      <Button size="small" onClick={() => setPreviewVersion(null)}>{t("actions.cancelPreview")}</Button>
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
              <Empty description={t("report.noReportData")} />
            )}
          </div>
          {versions.length > 0 && (
            <div style={{ width: 240 }}>
              <Card title={t("card.historyVersions")} size="small">
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
