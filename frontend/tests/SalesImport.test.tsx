import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SalesImport } from '../src/components/SalesImport';
import { request } from '../src/services/api';
import { catalog } from './fixtures';
import { SALES_CSV_HEADER } from '../src/services/salesCsv';
vi.mock('../src/services/api', () => ({ request: vi.fn() }));
const csv = `${SALES_CSV_HEADER}\nsale-1,1,2,1099.00,2026-10-03T10:00:00+05:30\nsale-2,1,1,1099.00,2026-10-03T11:00:00+05:30`;
const refresh = vi.fn();
function mount() { render(<SalesImport products={catalog.products} onImported={refresh} />); }
function file(name = 'sales.csv', value = csv) {
  const f = new File([value], name, { type: 'text/csv' });
  Object.defineProperty(f, 'text', { value: async () => value });
  return f;
}
beforeEach(() => { vi.mocked(request).mockReset(); refresh.mockClear(); });
describe('sales CSV input methods', () => {
  it('previews pasted text and imports only after explicit submission', async () => {
    vi.mocked(request).mockResolvedValue({ imported: 2, skipped: 0 }); mount();
    fireEvent.change(screen.getByLabelText('Paste CSV data'), { target: { value: csv } });
    fireEvent.click(screen.getByText('Preview pasted data'));
    expect(screen.getByText('2 sales · 3 units · ₹3,297.00 revenue')).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Import sales' }));
    expect(await screen.findByRole('status')).toHaveTextContent('2 sales imported; 0 matching records skipped');
    expect(request).toHaveBeenCalledWith('/api/v1/sales/import', undefined, { sales: [
      { reference: 'sale-1', product_id: 1, quantity: 2, unit_price: '1099.00', ordered_at: '2026-10-03T10:00:00+05:30' },
      { reference: 'sale-2', product_id: 1, quantity: 1, unit_price: '1099.00', ordered_at: '2026-10-03T11:00:00+05:30' },
    ] });
    expect(refresh).toHaveBeenCalledOnce();
  });
  it.each(['picker', 'drop', 'paste'])('stages a file from %s without importing', async method => {
    mount();
    const f = file();
    if (method === 'picker') fireEvent.change(screen.getByLabelText('Sales CSV'), { target: { files: [f] } });
    if (method === 'drop') fireEvent.drop(screen.getByRole('group'), { dataTransfer: { files: [f] } });
    if (method === 'paste') fireEvent.paste(screen.getByRole('group'), { clipboardData: { files: [f] } });
    expect(await screen.findByText('Preview: sales.csv')).toBeInTheDocument();
    expect(screen.getByLabelText('Paste CSV data')).toHaveValue(csv);
    expect(request).not.toHaveBeenCalled();
  });
  it('fills the example with a real product ID and price', () => {
    mount(); fireEvent.click(screen.getByText('Insert test example'));
    expect((screen.getByLabelText('Paste CSV data') as HTMLTextAreaElement).value).toContain(',1,2,999.00,');
    expect(screen.getByText('2 sales · 3 units · ₹2,997.00 revenue')).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });
  it('reports duplicate skips returned by the backend', async () => {
    vi.mocked(request).mockResolvedValue({ imported: 0, skipped: 2 }); mount();
    fireEvent.change(screen.getByLabelText('Paste CSV data'), { target: { value: csv } });
    fireEvent.click(screen.getByText('Preview pasted data')); fireEvent.click(screen.getByText('Import sales'));
    expect(await screen.findByRole('status')).toHaveTextContent('0 sales imported; 2 matching records skipped');
  });
  it('invalidates the preview when pasted text changes', () => {
    mount(); fireEvent.click(screen.getByText('Insert test example'));
    fireEvent.change(screen.getByLabelText('Paste CSV data'), { target: { value: 'invalid' } });
    expect(screen.queryByRole('button', { name: 'Import sales' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Preview pasted data'));
    expect(screen.getByRole('alert')).toHaveTextContent('first line');
  });
  it('handles import failure and permits retry', async () => {
    vi.mocked(request).mockRejectedValue(new Error('Store data unavailable')); mount();
    fireEvent.click(screen.getByText('Insert test example')); fireEvent.click(screen.getByText('Import sales'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Store data unavailable');
    expect(refresh).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('Import sales')).toBeEnabled());
  });
  it('rejects multiple files and non-CSV files', async () => {
    mount(); fireEvent.drop(screen.getByRole('group'), { dataTransfer: { files: [file(), file()] } });
    expect(screen.getByRole('alert')).toHaveTextContent('one CSV file');
    fireEvent.drop(screen.getByRole('group'), { dataTransfer: { files: [file('sales.xlsx')] } });
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a .csv file');
    expect(request).not.toHaveBeenCalled();
  });
});
