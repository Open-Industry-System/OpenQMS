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
          <Paragraph type="secondary">
            <Text strong>{t('wizard.guidance.labelExample')}：</Text>
            {t(`${prefix}.example`)}
          </Paragraph>
        </>
      )}
    </Card>
  );
}