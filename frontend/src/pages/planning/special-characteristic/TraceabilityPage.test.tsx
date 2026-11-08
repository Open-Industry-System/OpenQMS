import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import TraceabilityPage from './TraceabilityPage';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../../../api/client', () => ({ default: { get: mocks.get } }));

const chain = {
  sc_code: 'SC-1', sc_name: 'Diameter', sc_type: 'CC', sc_category: 'product',
  source_characteristic_id: 'characteristic-uuid', spec_requirement: '10±0.1',
  product_line_code: 'LINE', fmea_source: null, msa_study_id: null, msa_status: 'PENDING',
  control_plan_items: [
    { item_id: 'row-1', cp_id: 'cp-1', cp_document_no: 'CP-A', cp_title: 'First control', step_no: '10', process_name: 'Drill', characteristic_no: 'A', specification_tolerance: '10±0.1', requires_version_sync: true, guidance: 'Use formal version sync', gauge_id: 'gauge-1' },
    { item_id: 'row-2', cp_id: 'cp-2', cp_document_no: 'CP-B', cp_title: 'Second control', step_no: '10', process_name: 'Drill', characteristic_no: 'B', specification_tolerance: '10±0.1', requires_version_sync: false },
  ],
  spc_characteristics: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/list')
    ? { items: [{ sc_id: 'sc-1', sc_code: 'SC-1', sc_name: 'Diameter', sc_type: 'CC' }] } : chain }));
});

async function choose() {
  render(<MemoryRouter><TraceabilityPage /></MemoryRouter>);
  await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/special-characteristics/list'));
  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByText('SC-1 - Diameter (CC)'));
}

it('renders every derived control as a CP document link, characteristic identity and formal sync guidance', async () => {
  await choose();
  expect(await screen.findByRole('link', { name: 'CP-A' })).toHaveAttribute('href', '/control-plans/cp-1');
  expect(screen.getByRole('link', { name: 'CP-B' })).toHaveAttribute('href', '/control-plans/cp-2');
  expect(screen.getByText('characteristic-uuid')).toBeInTheDocument();
  expect(screen.getByText('Product Characteristic')).toBeInTheDocument();
  expect(screen.getByText('Use formal version sync')).toBeInTheDocument();
  expect(screen.getByText('No linked MSA study; calibration alone is not MSA evidence.')).toBeInTheDocument();
});

it('does not turn an absent MSA study into passed evidence even if a stale status says PASS', async () => {
  mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/list')
    ? { items: [{ sc_id: 'sc-1', sc_code: 'SC-1', sc_name: 'Diameter', sc_type: 'CC' }] }
    : { ...chain, msa_status: 'PASS' } }));
  await choose();
  expect(await screen.findByText('No linked MSA study; calibration alone is not MSA evidence.')).toBeInTheDocument();
  expect(screen.queryByText('PASS')).not.toBeInTheDocument();
});

it('shows the preserved safety material review warning without offering approval or force-sync actions', async () => {
  mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/list')
    ? { items: [{ sc_id: 'sc-1', sc_code: 'SC-1', sc_name: 'Diameter', sc_type: 'CC' }] }
    : { ...chain, review_required: true, review_message: 'Source changed; safety material preserved' } }));
  await choose();
  expect(await screen.findByText('Source changed; safety material preserved')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /approve|force/i })).not.toBeInTheDocument();
});

it('clearing a loading selection stops loading and ignores the late response', async () => {
  let resolve!: (value: unknown) => void;
  const pending = new Promise((r) => { resolve = r; });
  mocks.get.mockImplementation((url: string) => url.endsWith('/list')
    ? Promise.resolve({ data: { items: [{ sc_id: 'sc-1', sc_code: 'SC-1', sc_name: 'Diameter', sc_type: 'CC' }] } })
    : pending);
  await choose();
  await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/special-characteristics/traceability/sc-1'));
  fireEvent.mouseDown(screen.getByLabelText('close-circle'));
  await waitFor(() => expect(document.querySelector('.ant-spin')).toBeNull());
  await act(async () => resolve({ data: chain }));
  expect(screen.queryByRole('link', { name: 'CP-A' })).not.toBeInTheDocument();
});
