import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const STORAGE_KEY = 'dfmea_wizard_card_collapsed';

function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

interface WizardGuidanceCardProps {
  stepIndex: number;
}

export default function WizardGuidanceCard({ stepIndex }: WizardGuidanceCardProps) {
  const { t } = useTranslation('dfmea');
  const [collapsed, setCollapsed] = useState(getInitialCollapsed);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(STORAGE_KEY, String(next));
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