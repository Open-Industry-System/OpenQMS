import { useEffect, useState, useRef, useMemo } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Steps, Card, Form, Input,
  Select, App, Spin, Empty, Row, Col, Table, Divider, Modal,
} from "antd";
import { ArrowLeftOutlined, ArrowRightOutlined, LinkOutlined, PlusOutlined, DeleteOutlined, UndoOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getCAPA, updateCAPA, advanceCAPA, linkFMEA } from "../../api/capa";
import { getAIDraftCapabilities } from "../../api/capaDraft";
import { listFMEAs } from "../../api/fmea";
import RelatedFMEALink from "../../components/cross-links/RelatedFMEALink";
import D4RecPanel from "../../components/capa/D4RecPanel";
import D5RecPanel from "../../components/capa/D5RecPanel";
import D7RecPanel, { type D7UnconfirmedItem } from "../../components/capa/D7RecPanel";
import AIDraftButton from "../../components/capa/AIDraftButton";
import AIDraftPreview from "../../components/capa/AIDraftPreview";
import { useAIDraft } from "../../components/capa/useAIDraft";
import type { CAPAReport, FMEADocument, DraftFormat, LessonsLearnedResponse } from "../../types";
import LessonsLearnedModal from "../../components/lessons/LessonsLearnedModal";
import { getCAPALessons } from "../../api/lessonsLearned";
import axios from "axios";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";

const { Title, Text } = Typography;
const { TextArea } = Input;

const stepIndex: Record<string, number> = {
  D1_TEAM: 0, D2_DESCRIPTION: 1, D3_INTERIM: 2, D4_ROOT_CAUSE: 3,
  D5_CORRECTION: 4, D6_VERIFICATION: 5, D7_PREVENTION: 6, D8_CLOSURE: 7, ARCHIVED: 8,
};

export default function CAPADetailPage() {
  const { t } = useTranslation("capa");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [capa, setCapa] = useState<CAPAReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [_saving, setSaving] = useState(false);
  const [fmeas, setFmeas] = useState<FMEADocument[]>([]);
  const [linkModal, setLinkModal] = useState(false);

  const _user = useAuthStore((s) => s.user);
  const { canEdit, canApprove } = usePermission();

  const [localData, setLocalData] = useState<Record<string, any>>({});

  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("quality_engineer");

  const location = useLocation();
  const [lessonsModalOpen, setLessonsModalOpen] = useState(false);
  const [lessonsLoading, setLessonsLoading] = useState(false);
  const [lessonsData, setLessonsData] = useState<LessonsLearnedResponse | null>(null);
  const lessonsShownRef = useRef(false);

  const stepItems = useMemo(
    () => [
      { title: t("steps.d1") },
      { title: t("steps.d2") },
      { title: t("steps.d3") },
      { title: t("steps.d4") },
      { title: t("steps.d5") },
      { title: t("steps.d6") },
      { title: t("steps.d7") },
      { title: t("steps.d8") },
    ],
    [t]
  );

  const roleOptions = [
    { value: "quality_engineer", label: t("team.roles.quality_engineer") },
    { value: "process_engineer", label: t("team.roles.process_engineer") },
    { value: "rd_engineer", label: t("team.roles.rd_engineer") },
    { value: "project_manager", label: t("team.roles.project_manager") },
    { value: "production_supervisor", label: t("team.roles.production_supervisor") },
  ];

  useEffect(() => {
    if (location.state?.showLessonsLearned && !lessonsShownRef.current) {
      lessonsShownRef.current = true;
      setLessonsModalOpen(true);
      setLessonsLoading(true);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
        setLessonsLoading(false);
        setLessonsModalOpen(false);
        message.warning(t("messages.searchTimeout"));
      }, 10000);

      const problemDescription = location.state?.problemDescription;
      getCAPALessons(
        id!,
        problemDescription ? { problem_description: problemDescription } : undefined,
        { signal: controller.signal }
      )
        .then((res) => {
          clearTimeout(timeoutId);
          setLessonsData(res);
          setLessonsLoading(false);
        })
        .catch((err) => {
          clearTimeout(timeoutId);
          if (!axios.isCancel(err)) {
            message.error(t("messages.searchFailed"));
          }
          setLessonsLoading(false);
        });

      return () => {
        clearTimeout(timeoutId);
        controller.abort();
      };
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state, id]);

  const [allD7Confirmed, setAllD7Confirmed] = useState(true);
  const [d7UnconfirmedItems, setD7UnconfirmedItems] = useState<D7UnconfirmedItem[]>([]);
  const [d7SkipDialogOpen, setD7SkipDialogOpen] = useState(false);
  const [d7SkipReasons, setD7SkipReasons] = useState<Record<string, string>>({});

  const [aiDraftEnabled, setAiDraftEnabled] = useState(false);

  const {
    loading: draftLoading,
    draft,
    error: draftError,
    errorLevel,
    tempUnavailable,
    generate,
    clear,
    undo,
    saveUndo,
    canUndo,
  } = useAIDraft();
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    if (draft && !draftLoading) {
      setPreviewOpen(true);
    }
  }, [draft, draftLoading]);

  useEffect(() => {
    if (!draftError || draftLoading) return;
    if (errorLevel === "error") {
      message.error(draftError);
    } else {
      message.warning(draftError);
    }
  }, [draftError, errorLevel, draftLoading, message]);

  useEffect(() => {
    if (!id) return;
    getCAPA(id).then(setCapa).finally(() => setLoading(false));
    listFMEAs({ page_size: 100 }).then((res) => setFmeas(res.items));
    getAIDraftCapabilities()
      .then((caps) => setAiDraftEnabled(caps.ai_draft_enabled))
      .catch(() => setAiDraftEnabled(false));
  }, [id]);

  useEffect(() => {
    if (capa) {
      setLocalData({
        d1_team: capa.d1_team || [],
        d2_description: capa.d2_description || "",
        d3_interim: capa.d3_interim || "",
        d4_root_cause: capa.d4_root_cause || "",
        d5_correction: capa.d5_correction || "",
        d6_verification: capa.d6_verification || "",
        d7_prevention: capa.d7_prevention || "",
        d8_closure: capa.d8_closure || "",
      });
    }
  }, [capa]);

  const currentStep = capa ? (stepIndex[capa.status] ?? 0) : 0;

  const handleUpdate = async (field: string, value: unknown, throwOnError = false) => {
    if (!id || !canEdit('capa')) return;

    if (capa && JSON.stringify(capa[field as keyof CAPAReport]) === JSON.stringify(value)) {
      return;
    }

    setSaving(true);
    try {
      const updated = await updateCAPA(id, { [field]: value });
      setCapa(updated);
    } catch (e) {
      message.error(tc("messages.saveFailed"));
      if (throwOnError) throw e;
    } finally {
      setSaving(false);
    }
  };

  const stepToField: Record<string, string> = {
    d2: "d2_description", d3: "d3_interim", d4: "d4_root_cause",
    d5: "d5_correction", d6: "d6_verification", d7: "d7_prevention", d8: "d8_closure",
  };

  const handleGenerate = (step: string, format: DraftFormat) => {
    if (!id) return;
    clear();
    generate(id, step, format);
  };

  const handleReplace = async () => {
    if (!draft) return;
    const field = stepToField[draft.step];
    if (!field) return;
    const originalValue = localData[field] || "";
    saveUndo(field, originalValue);
    setLocalData((p) => ({ ...p, [field]: draft.content }));
    try {
      await handleUpdate(field, draft.content, true);
    } catch {
      setLocalData((p) => ({ ...p, [field]: originalValue }));
      return;
    }
    setPreviewOpen(false);
    clear();
  };

  const handleAppend = async () => {
    if (!draft) return;
    const field = stepToField[draft.step];
    if (!field) return;
    const originalValue = localData[field] || "";
    const appended = originalValue ? `${originalValue}\n\n${draft.content}` : draft.content;
    saveUndo(field, originalValue);
    setLocalData((p) => ({ ...p, [field]: appended }));
    try {
      await handleUpdate(field, appended, true);
    } catch {
      setLocalData((p) => ({ ...p, [field]: originalValue }));
      return;
    }
    setPreviewOpen(false);
    clear();
  };

  const handleUndo = (field: string) => {
    const prev = undo(field);
    if (prev !== undefined) {
      setLocalData((p) => ({ ...p, [field]: prev }));
      handleUpdate(field, prev);
      message.success(t("messages.undoSuccess"));
    }
  };

  const renderLabelWithDraft = (step: string, label: string) => {
    const field = stepToField[step];
    const hasHistory = canUndo(field);
    const showAIButton = aiDraftEnabled && canEdit('capa');
    return (
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>{label}</span>
        <Space size="small">
          {hasHistory && (
            <Button
              size="small"
              type="link"
              icon={<UndoOutlined />}
              onClick={() => handleUndo(field)}
            >
              {t("actions.undoChange")}
            </Button>
          )}
          {showAIButton && (
            <AIDraftButton
              loading={draftLoading}
              tempUnavailable={tempUnavailable}
              error={errorLevel === "error" ? draftError : null}
              onGenerate={(format) => handleGenerate(step, format)}
            />
          )}
        </Space>
      </div>
    );
  };

  const handleAdvance = async () => {
    if (!id) return;

    if (capa?.status === "D7_PREVENTION" && !allD7Confirmed) {
      setD7SkipDialogOpen(true);
      return;
    }

    try {
      const updated = await advanceCAPA(id);
      setCapa(updated);
      message.success(t("messages.advanceSuccess"));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.advanceFailed"));
    }
  };

  const handleD7SkipConfirm = async () => {
    if (!id) return;
    setD7SkipDialogOpen(false);

    const globalReason = (d7SkipReasons["__global__"] || "").trim();
    const skipReasonsList = d7UnconfirmedItems.map((item) => ({
      fmea_id: item.fmea_id,
      node_id: item.failure_mode_node_id,
      reason: globalReason || t("d7.skipReasonEmpty"),
    }));

    try {
      const updated = await advanceCAPA(id, {
        d7_skip_reasons: skipReasonsList.length > 0 ? skipReasonsList : undefined,
      });
      setCapa(updated);
      message.success(t("messages.advanceSuccess"));
      setD7SkipReasons({});
      setD7UnconfirmedItems([]);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.advanceFailed"));
    }
  };

  const handleLinkFMEA = async (fmeaId: string) => {
    if (!id) return;
    try {
      const updated = await linkFMEA(id, fmeaId);
      setCapa(updated);
      setLinkModal(false);
      message.success(t("messages.linkFMEASuccess"));
    } catch { message.error(t("messages.linkFMEAFailed")); }
  };

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!capa) return <Empty description={t("messages.capaNotFound")} />;

  return (
    <>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/capa")}>{tc("actions.back")}</Button>
            <Title level={4} style={{ margin: 0 }}>{capa.title}</Title>
            <Tag color="blue">{capa.document_no}</Tag>
            <Tag color="red">{t(`severity.${capa.severity}`, capa.severity)}</Tag>
          </Space>
          <Space>
            {capa.fmea_ref_id && (
              <Tag icon={<LinkOutlined />} color="green">{t("fmea.linked")}</Tag>
            )}
            <RelatedFMEALink
              fmeaRefId={capa.fmea_ref_id ?? null}
              fmeaNodeId={capa.fmea_node_id ?? null}
            />
            {canEdit('capa') && (
              <Button icon={<LinkOutlined />} onClick={() => setLinkModal(true)}>
                {capa.fmea_ref_id ? t("fmea.changeFMEA") : t("fmea.linkFMEA")}
              </Button>
            )}
            {capa.status !== "ARCHIVED" && capa.status !== "D8_CLOSURE" && (!["D7_PREVENTION", "D8_CLOSURE"].includes(capa.status) || canApprove('capa')) && canEdit('capa') && (
              <Button type="primary" icon={<ArrowRightOutlined />} onClick={handleAdvance}>
                {t("actions.advance")}
              </Button>
            )}
          </Space>
        </div>

        <Steps current={currentStep} items={stepItems} style={{ marginBottom: 24 }} />

        <Row gutter={16}>
          <Col span={16}>
            <Card title={t("detail.currentStepDetails")}>
            {capa.status === "D1_TEAM" && (
              <div>
                <Table
                  dataSource={localData.d1_team || []}
                  rowKey="name"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: t("team.name"), dataIndex: "name", key: "name" },
                    { title: t("team.role"), dataIndex: "role", key: "role" },
                    {
                      title: tc("table.operations"),
                      key: "action",
                      width: 80,
                      render: (_, record: any) => (
                        <Button
                          type="text"
                          danger
                          disabled={!canEdit('capa')}
                          icon={<DeleteOutlined />}
                          onClick={() => {
                            const filtered = (localData.d1_team || []).filter(
                              (m: any) => m.name !== record.name
                            );
                            handleUpdate("d1_team", filtered);
                          }}
                        />
                      ),
                    },
                  ]}
                />
                {canEdit('capa') && (
                  <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
                    <Input
                      placeholder={t("team.namePlaceholder")}
                      value={newMemberName}
                      onChange={(e) => setNewMemberName(e.target.value)}
                      style={{ width: 150 }}
                    />
                    <Select
                      value={newMemberRole}
                      onChange={(val) => setNewMemberRole(val)}
                      style={{ width: 150 }}
                      options={roleOptions}
                    />
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        if (!newMemberName.trim()) {
                          message.warning(t("messages.enterName"));
                          return;
                        }
                        const exists = (localData.d1_team || []).some(
                          (m: any) => m.name === newMemberName.trim()
                        );
                        if (exists) {
                          message.warning(t("messages.memberExists"));
                          return;
                        }
                        const newTeam = [
                          ...(localData.d1_team || []),
                          { name: newMemberName.trim(), role: newMemberRole },
                        ];
                        handleUpdate("d1_team", newTeam);
                        setNewMemberName("");
                      }}
                    >
                      {t("actions.addMember")}
                    </Button>
                  </div>
                )}
              </div>
            )}

            {capa.status === "D2_DESCRIPTION" && (
              <Form layout="vertical">
                <Form.Item label={renderLabelWithDraft("d2", t("fields.d2Label"))}>
                  <TextArea
                    rows={6}
                    disabled={!canEdit('capa')}
                    value={localData.d2_description || ""}
                    onChange={(e) => setLocalData({ ...localData, d2_description: e.target.value })}
                    onBlur={() => handleUpdate("d2_description", localData.d2_description)}
                    placeholder="What / Who / When / Where / Why / How / How much"
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D3_INTERIM" && (
              <Form layout="vertical">
                <Form.Item label={renderLabelWithDraft("d3", t("fields.d3Label"))}>
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d3_interim || ""}
                    onChange={(e) => setLocalData({ ...localData, d3_interim: e.target.value })}
                    onBlur={() => handleUpdate("d3_interim", localData.d3_interim)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D4_ROOT_CAUSE" && (
              <>
                <D4RecPanel
                  capaId={id!}
                  canAdopt={canEdit('capa')}
                  onAdopt={(text) => {
                    const current = localData.d4_root_cause || "";
                    const newVal = current ? `${current}\n${text}` : text;
                    setLocalData({ ...localData, d4_root_cause: newVal });
                    handleUpdate("d4_root_cause", newVal);
                  }}
                />
                <Form layout="vertical">
                  <Form.Item label={renderLabelWithDraft("d4", t("fields.d4Label"))}>
                    <TextArea
                      rows={6}
                      disabled={!canEdit('capa')}
                      value={localData.d4_root_cause || ""}
                      onChange={(e) => setLocalData({ ...localData, d4_root_cause: e.target.value })}
                      onBlur={() => handleUpdate("d4_root_cause", localData.d4_root_cause)}
                    />
                  </Form.Item>
                </Form>
              </>
            )}

            {capa.status === "D5_CORRECTION" && (
              <>
                <D5RecPanel
                  capaId={id!}
                  canAdopt={canEdit('capa')}
                  onAdopt={(text) => {
                    const current = localData.d5_correction || "";
                    const newVal = current ? `${current}\n${text}` : text;
                    setLocalData({ ...localData, d5_correction: newVal });
                    handleUpdate("d5_correction", newVal);
                  }}
                />
                <Form layout="vertical">
                  <Form.Item label={renderLabelWithDraft("d5", t("fields.d5Label"))}>
                    <TextArea
                      rows={4}
                      disabled={!canEdit('capa')}
                      value={localData.d5_correction || ""}
                      onChange={(e) => setLocalData({ ...localData, d5_correction: e.target.value })}
                      onBlur={() => handleUpdate("d5_correction", localData.d5_correction)}
                    />
                  </Form.Item>
                </Form>
              </>
            )}

            {capa.status === "D6_VERIFICATION" && (
              <Form layout="vertical">
                <Form.Item label={renderLabelWithDraft("d6", t("fields.d6Label"))}>
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d6_verification || ""}
                    onChange={(e) => setLocalData({ ...localData, d6_verification: e.target.value })}
                    onBlur={() => handleUpdate("d6_verification", localData.d6_verification)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D7_PREVENTION" && (
              <>
                <Form layout="vertical">
                  <Form.Item label={renderLabelWithDraft("d7", t("fields.d7Label"))}>
                    <TextArea
                      rows={4}
                      disabled={!canEdit('capa')}
                      value={localData.d7_prevention || ""}
                      onChange={(e) => setLocalData({ ...localData, d7_prevention: e.target.value })}
                      onBlur={() => handleUpdate("d7_prevention", localData.d7_prevention)}
                    />
                  </Form.Item>
                </Form>
                <Divider />
                <D7RecPanel
                  capaId={id!}
                  d5Correction={localData.d5_correction}
                  onConfirmationChange={(allConfirmed, unconfirmed) => {
                    setAllD7Confirmed(allConfirmed);
                    setD7UnconfirmedItems(unconfirmed);
                  }}
                />
              </>
            )}

            {capa.status === "D8_CLOSURE" && (
              <Form layout="vertical">
                <Form.Item label={renderLabelWithDraft("d8", t("fields.d8Label"))}>
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d8_closure || ""}
                    onChange={(e) => setLocalData({ ...localData, d8_closure: e.target.value })}
                    onBlur={() => handleUpdate("d8_closure", localData.d8_closure)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "ARCHIVED" && <Empty description={t("messages.reportArchived")} />}
          </Card>
        </Col>

        <Col span={8}>
          <Card title={t("detail.reportInfo")} size="small">
            <p><Text strong>{t("detail.documentNo")}</Text> {capa.document_no}</p>
            <p><Text strong>{t("detail.severity")}</Text> <Tag color="red">{t(`severity.${capa.severity}`, capa.severity)}</Tag></p>
            <p><Text strong>{t("detail.dueDate")}</Text> {capa.due_date || t("detail.notSet")}</p>
            <p><Text strong>{t("detail.relatedFMEA")}</Text> {capa.fmea_ref_id || t("detail.notLinked")}</p>
            <p><Text strong>{t("detail.createdAt")}</Text> {new Date(capa.created_at).toLocaleString()}</p>
          </Card>

          {linkModal && canEdit('capa') && (
            <Card title={t("fmea.selectTitle")} size="small" style={{ marginTop: 16 }}>
              <Select
                showSearch
                style={{ width: "100%" }}
                placeholder={t("fmea.searchPlaceholder")}
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
                options={fmeas.map((f) => ({
                  value: f.fmea_id,
                  label: `${f.document_no} - ${f.title}`,
                }))}
                onChange={(val) => handleLinkFMEA(val)}
              />
              <Button style={{ marginTop: 8 }} onClick={() => setLinkModal(false)}>{tc("actions.cancel")}</Button>
            </Card>
          )}
        </Col>
      </Row>
      </div>

      <Modal
        title={t("d7.skipDialogTitle")}
        open={d7SkipDialogOpen}
        onOk={handleD7SkipConfirm}
        onCancel={() => setD7SkipDialogOpen(false)}
        okText={t("d7.skipConfirm")}
        cancelText={tc("actions.cancel")}
        width={600}
      >
        <p>{t("d7.skipDialogDescription")}</p>
        <ul>
          {d7UnconfirmedItems.map((item) => (
            <li key={item.failure_mode_node_id}>
              {item.failure_mode_name}
              {item.failure_cause_node_id && `${t("d7.causeLabel")}${item.failure_cause_node_id}`}
            </li>
          ))}
        </ul>
        <p>{t("d7.skipReasonLabel")}</p>
        <Input.TextArea
          rows={3}
          placeholder={t("d7.skipReasonPlaceholder")}
          value={d7SkipReasons["__global__"] || ""}
          onChange={(e) =>
            setD7SkipReasons({ ...d7SkipReasons, __global__: e.target.value })
          }
        />
      </Modal>

      <AIDraftPreview
        open={previewOpen}
        content={draft?.content || ""}
        onClose={() => {
          setPreviewOpen(false);
          clear();
        }}
        onReplace={handleReplace}
        onAppend={handleAppend}
      />
      <LessonsLearnedModal
        open={lessonsModalOpen}
        loading={lessonsLoading}
        data={lessonsData}
        onClose={() => setLessonsModalOpen(false)}
        onViewDetail={(card) => {
          if (card.source_type === "fmea") {
            window.open(`/fmea/${card.source_id}`, "_blank");
          } else if (card.source_type === "capa") {
            window.open(`/capa/${card.source_id}`, "_blank");
          } else if (card.source_type === "audit") {
            const auditId = card.metadata?.audit_id;
            const category = card.metadata?.audit_category;
            if (auditId) {
              const path = category === "customer" ? `/customer-audits/${auditId}` : `/internal-audits/${auditId}`;
              window.open(path, "_blank");
            }
          }
        }}
      />
    </>
  );
}
