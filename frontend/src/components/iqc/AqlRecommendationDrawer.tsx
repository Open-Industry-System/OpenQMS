import { useState, useMemo } from 'react';
import { Drawer, Descriptions, Tag, Button, Space, App, Divider, List, Input } from 'antd';
import { useTranslation } from 'react-i18next';
import type { AqlRecommendation } from '../../types';
import {
  engineerApproveRecommendation,
  engineerRejectRecommendation,
  forwardRecommendation,
  managerApproveRecommendation,
  managerRejectRecommendation,
} from '../../api/iqcAql';
import { useAuthStore } from '../../store/authStore';

interface Props {
  open: boolean;
  recommendation: AqlRecommendation | null;
  onClose: () => void;
  onAction: () => void;
}

export default function AqlRecommendationDrawer({ open, recommendation, onClose, onAction }: Props) {
  const { t, i18n } = useTranslation('iqc');
  const { t: tc } = useTranslation('common');
  const { message, modal: _modal } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);

  const directionMap = useMemo<Record<string, { label: string; color: string }>>(
    () => ({
      keep: { label: t('status.recDirection.keep'), color: 'default' },
      reduce: { label: t('status.recDirection.reduce'), color: 'green' },
      tighten: { label: t('status.recDirection.tighten'), color: 'orange' },
      freeze: { label: t('status.recDirection.freeze'), color: 'red' },
    }),
    [t]
  );

  const statusMap = useMemo<Record<string, { label: string; color: string }>>(
    () => ({
      pending: { label: t('status.recStatus.pending'), color: 'orange' },
      forwarded: { label: t('status.recStatus.forwarded'), color: 'blue' },
      approved: { label: t('status.recStatus.approved'), color: 'green' },
      effective: { label: t('status.recStatus.effective'), color: 'green' },
      rejected: { label: t('status.recStatus.rejected'), color: 'red' },
      expired: { label: t('status.recStatus.expired'), color: 'default' },
    }),
    [t]
  );

  if (!recommendation) return null;

  const isEngineer = user?.role_key === 'quality_engineer' || user?.role_key === 'engineer';
  const isManager = user?.role_key === 'manager' || user?.role_key === 'admin';
  const isReduce = recommendation.direction === 'reduce';
  const canEngineerAct = recommendation.status === 'pending' && isEngineer;
  const canManagerAct = recommendation.status === 'forwarded' && isManager;

  const handleAction = async (action: () => Promise<AqlRecommendation>, successMsg: string) => {
    setActionLoading(true);
    try {
      await action();
      message.success(successMsg);
      setShowReject(false);
      setRejectReason('');
      onAction();
    } catch {
      message.error(tc('messages.operationFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  const doReject = (actionFn: (id: string, reason: string) => Promise<AqlRecommendation>) => {
    if (!rejectReason.trim()) {
      message.error(t('messages.enterRejectReason'));
      return;
    }
    handleAction(() => actionFn(recommendation.recommendation_id, rejectReason.trim()), t('messages.rejected'));
  };

  const dir = directionMap[recommendation.direction] || { label: recommendation.direction, color: 'default' };
  const st = statusMap[recommendation.status] || { label: recommendation.status, color: 'default' };

  const evidence = recommendation.evidence as Record<string, unknown> | null;

  const formatDateTime = (v: string) => v ? new Date(v).toLocaleString(i18n.language) : '—';

  return (
    <Drawer
      title={t('drawer.recommendationDetail')}
      open={open}
      onClose={onClose}
      width={640}
    >
      <Descriptions column={2} bordered size="small">
        <Descriptions.Item label={t('table.currentAql')}>{recommendation.current_aql}</Descriptions.Item>
        <Descriptions.Item label={t('table.recommendedAql')}>{recommendation.recommended_aql}</Descriptions.Item>
        <Descriptions.Item label={t('table.direction')}><Tag color={dir.color}>{dir.label}</Tag></Descriptions.Item>
        <Descriptions.Item label={t('recommendation.approvalLevel')}>{recommendation.approval_level === 'manager' ? t('status.approvalLevel.manager') : t('status.approvalLevel.engineer')}</Descriptions.Item>
        <Descriptions.Item label={t('table.status')}><Tag color={st.color}>{st.label}</Tag></Descriptions.Item>
        <Descriptions.Item label={t('table.createdAt')}>{formatDateTime(recommendation.created_at)}</Descriptions.Item>
        <Descriptions.Item label={t('recommendation.expiresAt')} span={2}>{formatDateTime(recommendation.expires_at)}</Descriptions.Item>
      </Descriptions>

      {evidence && (
        <>
          <Divider orientation="left" orientationMargin={0}>{t('recommendation.qualitySnapshot')}</Divider>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label={t('descriptions.totalBatches')}>{String(evidence.total_batches ?? '—')}</Descriptions.Item>
            <Descriptions.Item label={t('descriptions.consecutiveAccepted')}>{String(evidence.consecutive_accepted ?? '—')}</Descriptions.Item>
            <Descriptions.Item label={t('descriptions.consecutiveRejected')}>{String(evidence.consecutive_rejected ?? '—')}</Descriptions.Item>
            <Descriptions.Item label={t('descriptions.last30dPpm')}>{evidence.last_30d_ppm != null ? String(evidence.last_30d_ppm) : '—'}</Descriptions.Item>
          </Descriptions>
        </>
      )}

      {recommendation.trigger_rules.length > 0 && (
        <>
          <Divider orientation="left" orientationMargin={0}>{t('recommendation.triggerRules')}</Divider>
          <List
            size="small"
            dataSource={recommendation.trigger_rules}
            renderItem={(rule) => (
              <List.Item>
                <Tag>{rule.rule_id}</Tag> {rule.reason}
              </List.Item>
            )}
          />
        </>
      )}

      {(canEngineerAct || canManagerAct) && (
        <>
          <Divider />
          {showReject && (
            <div style={{ marginBottom: 12 }}>
              <Input.TextArea
                rows={3}
                placeholder={t('messages.enterRejectReason')}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </div>
          )}
          <Space>
            {canEngineerAct && !isReduce && (
              <Button type="primary" loading={actionLoading} onClick={() => handleAction(() => engineerApproveRecommendation(recommendation.recommendation_id), t('messages.approved'))}>
                {t('recommendation.approve')}
              </Button>
            )}
            {canEngineerAct && isReduce && (
              <Button type="primary" loading={actionLoading} onClick={() => handleAction(() => forwardRecommendation(recommendation.recommendation_id), t('messages.submittedToManager'))}>
                {t('recommendation.submitToManager')}
              </Button>
            )}
            {canEngineerAct && !showReject && (
              <Button danger onClick={() => setShowReject(true)}>
                {t('recommendation.reject')}
              </Button>
            )}
            {canEngineerAct && showReject && (
              <Button danger loading={actionLoading} onClick={() => doReject(engineerRejectRecommendation)}>
                {t('recommendation.confirmReject')}
              </Button>
            )}
            {canManagerAct && (
              <Button type="primary" loading={actionLoading} onClick={() => handleAction(() => managerApproveRecommendation(recommendation.recommendation_id), t('messages.approved'))}>
                {t('recommendation.approve')}
              </Button>
            )}
            {canManagerAct && !showReject && (
              <Button danger onClick={() => setShowReject(true)}>
                {t('recommendation.reject')}
              </Button>
            )}
            {canManagerAct && showReject && (
              <Button danger loading={actionLoading} onClick={() => doReject(managerRejectRecommendation)}>
                {t('recommendation.confirmReject')}
              </Button>
            )}
            {showReject && (
              <Button onClick={() => { setShowReject(false); setRejectReason(''); }}>{tc('actions.cancel')}</Button>
            )}
          </Space>
        </>
      )}
    </Drawer>
  );
}
