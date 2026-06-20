import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from 'antd';
import GenerationWizard from './GenerationWizard';

describe('GenerationWizard Step 0 scope', () => {
  it('shows a visible Timeframe label and a range picker', () => {
    render(
      <App>
        <GenerationWizard open={true} onCancel={() => {}} onComplete={() => {}} />
      </App>
    );
    // Visible label (i18n is en-US in tests) — a placeholder is NOT matched by getByText,
    // so this only passes once a real label node exists.
    expect(screen.getByText('Timeframe')).toBeInTheDocument();
    // antd RangePicker portals to document.body, so query document (not the render container).
    expect(document.querySelector('.ant-picker-range')).not.toBeNull();
  });
});
