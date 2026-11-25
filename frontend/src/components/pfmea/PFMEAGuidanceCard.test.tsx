import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import PFMEAGuidanceCard from './PFMEAGuidanceCard';
import { I18nTestWrapper } from './__test-utils__/I18nWrapper';

describe('PFMEAGuidanceCard', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  it('renders the step0 title from pfmea namespace', () => {
    render(<PFMEAGuidanceCard stepIndex={0} />, { wrapper: I18nTestWrapper });
    expect(screen.getAllByText(/5T-Umfang/i).length).toBeGreaterThan(0);
  });
  it('renders step1 fields mentioning 4M or 工序号', () => {
    render(<PFMEAGuidanceCard stepIndex={1} />, { wrapper: I18nTestWrapper });
    expect(screen.getAllByText(/Prozess-Nr\. OPxx|4M-Klassifizierung/i).length).toBeGreaterThan(0);
  });
  it('expands by default when no preference is stored', () => {
    render(<PFMEAGuidanceCard stepIndex={0} />, { wrapper: I18nTestWrapper });
    expect(screen.getAllByText(/5T-Umfang/i).length).toBeGreaterThan(0);
    expect(screen.queryByText('Aufklappen')).toBeNull();
  });
  it('expands by default even if an old version stored an explicit false', () => {
    localStorage.setItem('pfmea_wizard_card_collapsed', 'false');
    render(<PFMEAGuidanceCard stepIndex={0} />, { wrapper: I18nTestWrapper });
    expect(screen.getAllByText(/5T-Umfang/i).length).toBeGreaterThan(0);
    expect(screen.queryByText('Aufklappen')).toBeNull();
  });
  it('stays collapsed only when the user explicitly collapsed it', () => {
    localStorage.setItem('pfmea_wizard_card_collapsed', 'true');
    render(<PFMEAGuidanceCard stepIndex={0} />, { wrapper: I18nTestWrapper });
    expect(screen.getByText('Aufklappen')).toBeTruthy();
  });
});
