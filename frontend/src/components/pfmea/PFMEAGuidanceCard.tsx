import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const STORAGE_KEY = 'pfmea_wizard_card_collapsed';

function getInitialCollapsed(): boolean {
  // 默认展开：仅当用户明确收起过（存储 'true'）才收起；旧版本存过 'false' 的按未设置处理
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

interface PFMEAGuidanceCardProps {
  stepIndex: number;
}

export default function PFMEAGuidanceCard({ stepIndex }: PFMEAGuidanceCardProps) {
  const { t } = useTranslation('pfmea');
  const [collapsed, setCollapsed] = useState(getInitialCollapsed);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      // 仅记录"用户收起过"这一偏好；展开是默认态，不持久化
      if (next) {
        localStorage.setItem(STORAGE_KEY, 'true');
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // ignore write failures
    }
  };

  const prefix = `wizard.guidance.step${stepIndex}`;
  const title = t(`${prefix}.title`);

  // Per-field fill-in guidance (array of {name, desc}) — empty if absent
  const fieldsRaw = t(`${prefix}.fields`, { returnObjects: true }) as unknown as { name: string; desc: string }[] | string;
  const fields: { name: string; desc: string }[] = Array.isArray(fieldsRaw) ? fieldsRaw : [];

  return (
    <Card
      size="small"
      title={title}
      aria-expanded={!collapsed}
      extra={
        <a
          onClick={toggle}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              toggle();
            }
          }}
        >
          {collapsed ? t('wizard.guidance.expand') : t('wizard.guidance.collapse')}
        </a>
      }
    >
      {!collapsed && (
        <>
          <Paragraph>
            <Text strong>{t('wizard.guidance.labelPurpose')}：</Text>
            {t(`${prefix}.purpose`)}
          </Paragraph>
          <Paragraph>
            <Text strong>{t('wizard.guidance.labelPoints')}：</Text>
            {t(`${prefix}.points`)}
          </Paragraph>

          {fields.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Paragraph style={{ marginBottom: 8 }}>
                <Text strong>{t('wizard.guidance.labelFields')}：</Text>
              </Paragraph>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {fields.map((f, i) => (
                  <li key={i} style={{ marginBottom: 6, lineHeight: 1.6 }}>
                    <Text strong style={{ color: 'var(--qf-cyan)' }}>{f.name}</Text>
                    <span style={{ color: 'var(--qf-text-secondary)' }}>：{f.desc}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <Paragraph type="secondary">
            <Text strong>{t('wizard.guidance.labelExample')}：</Text>
            {t(`${prefix}.example`)}
          </Paragraph>
        </>
      )}
    </Card>
  );
}
