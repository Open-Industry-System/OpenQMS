import { useState } from 'react';
import { Drawer, Descriptions, Tag, Button, Space, App, Divider, List, Input } from 'antd';
import type { AqlRecommendation } from '../../types';
import {
  engineerApproveRecommendation,
  engineerRejectRecommendation,
  forwardRecommendation,
  managerApproveRecommendation,
  managerRejectRecommendation,
} from '../../api/iqcAql';
import { useAuthStore } from '../../store/authStore';

const DIRECTION_MAP: Record<string, { label: string; color: string }> = {
  keep: { label: '保持', color: 'default' },
  reduce: { label: '放宽', color: 'green' },
  tighten: { label: '加严', color: 'orange' },
  freeze: { label: '冻结', color: 'red' },
};

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审批', color: 'orange' },
  forwarded: { label: '已转交', color: 'blue' },
  approved: { label: '已批准', color: 'green' },
  effective: { label: '已生效', color: 'green' },
  rejected: { label: '已拒绝', color: 'red' },
  expired: { label: '已过期', color: 'default' },
};

interface Props {
  open: boolean;
  recommendation: AqlRecommendation | null;
  onClose: () => void;
  onAction: () => void;
}

export default function AqlRecommendationDrawer({ open, recommendation, onClose, onAction }: Props) {
  const { message, modal: _modal } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);

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
      message.error('操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  const doReject = (actionFn: (id: string, reason: string) => Promise<AqlRecommendation>) => {
    if (!rejectReason.trim()) {
      message.error('请填写拒绝原因');
      return;
    }
    handleAction(() => actionFn(recommendation.recommendation_id, rejectReason.trim()), '已拒绝');
  };

  const dir = DIRECTION_MAP[recommendation.direction] || { label: recommendation.direction, color: 'default' };
  const st = STATUS_MAP[recommendation.status] || { label: recommendation.status, color: 'default' };

  const evidence = recommendation.evidence as Record<string, unknown> | null;

  return (
    <Drawer
      title="建议详情"
      open={open}
      onClose={onClose}
      width={640}
    >
      <Descriptions column={2} bordered size="small">
        <Descriptions.Item label="当前AQL">{recommendation.current_aql}</Descriptions.Item>
        <Descriptions.Item label="建议AQL">{recommendation.recommended_aql}</Descriptions.Item>
        <Descriptions.Item label="方向"><Tag color={dir.color}>{dir.label}</Tag></Descriptions.Item>
        <Descriptions.Item label="审批级别">{recommendation.approval_level === 'manager' ? '经理' : '工程师'}</Descriptions.Item>
        <Descriptions.Item label="状态"><Tag color={st.color}>{st.label}</Tag></Descriptions.Item>
        <Descriptions.Item label="创建时间">{new Date(recommendation.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
        <Descriptions.Item label="过期时间" span={2}>{new Date(recommendation.expires_at).toLocaleString('zh-CN')}</Descriptions.Item>
      </Descriptions>

      {evidence && (
        <>
          <Divider orientation="left" orientationMargin={0}>质量快照</Divider>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="总批次数">{String(evidence.total_batches ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="连续合格">{String(evidence.consecutive_accepted ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="连续不合格">{String(evidence.consecutive_rejected ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="30天PPM">{evidence.last_30d_ppm != null ? String(evidence.last_30d_ppm) : '—'}</Descriptions.Item>
          </Descriptions>
        </>
      )}

      {recommendation.trigger_rules.length > 0 && (
        <>
          <Divider orientation="left" orientationMargin={0}>触发规则</Divider>
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
                placeholder="拒绝原因（必填）"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </div>
          )}
          <Space>
            {canEngineerAct && !isReduce && (
              <Button type="primary" loading={actionLoading} onClick={() => handleAction(() => engineerApproveRecommendation(recommendation.recommendation_id), '已批准')}>
                批准
              </Button>
            )}
            {canEngineerAct && isReduce && (
              <Button type="primary" loading={actionLoading} onClick={() => handleAction(() => forwardRecommendation(recommendation.recommendation_id), '已提交经理')}>
                提交经理
              </Button>
            )}
            {canEngineerAct && !showReject && (
              <Button danger onClick={() => setShowReject(true)}>
                拒绝
              </Button>
            )}
            {canEngineerAct && showReject && (
              <Button danger loading={actionLoading} onClick={() => doReject(engineerRejectRecommendation)}>
                确认拒绝
              </Button>
            )}
            {canManagerAct && (
              <Button type="primary" loading={actionLoading} onClick={() => handleAction(() => managerApproveRecommendation(recommendation.recommendation_id), '已批准')}>
                批准
              </Button>
            )}
            {canManagerAct && !showReject && (
              <Button danger onClick={() => setShowReject(true)}>
                拒绝
              </Button>
            )}
            {canManagerAct && showReject && (
              <Button danger loading={actionLoading} onClick={() => doReject(managerRejectRecommendation)}>
                确认拒绝
              </Button>
            )}
            {showReject && (
              <Button onClick={() => { setShowReject(false); setRejectReason(''); }}>取消</Button>
            )}
          </Space>
        </>
      )}
    </Drawer>
  );
}
