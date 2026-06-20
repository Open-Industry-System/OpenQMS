import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import GenerationWizard from './GenerationWizard';

describe('GenerationWizard Step 0 scope', () => {
  it('shows a visible Timeframe label and a range picker', async () => {
    render(
      <App>
        <GenerationWizard open={true} onCancel={() => {}} onComplete={() => {}} />
      </App>
    );
    // Visible label (i18n is en-US in tests). antd Modal portals to document.body and its
    // render/portal timing in jsdom can be async, so wait for the label node to appear.
    // A placeholder is NOT matched by getByText, so this only passes once a real label exists.
    await waitFor(() => expect(screen.getByText('Timeframe')).toBeInTheDocument());
    // RangePicker is in the same portal tree as the label, so it's present once the label is.
    expect(document.querySelector('.ant-picker-range')).not.toBeNull();
  });
});
