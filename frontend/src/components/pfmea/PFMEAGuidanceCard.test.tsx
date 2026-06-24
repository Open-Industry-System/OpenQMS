import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PFMEAGuidanceCard from './PFMEAGuidanceCard';
import { I18nTestWrapper } from './__test-utils__/I18nWrapper';

describe('PFMEAGuidanceCard', () => {
  it('renders the step0 title from pfmea namespace', () => {
    render(<PFMEAGuidanceCard stepIndex={0} />, { wrapper: I18nTestWrapper });
    expect(screen.getAllByText(/5T范围/i).length).toBeGreaterThan(0);
  });
  it('renders step1 fields mentioning 4M or 工序号', () => {
    render(<PFMEAGuidanceCard stepIndex={1} />, { wrapper: I18nTestWrapper });
    expect(screen.getAllByText(/工序号 OPxx|4M分类/i).length).toBeGreaterThan(0);
  });
});
