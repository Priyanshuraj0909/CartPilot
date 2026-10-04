import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProductTable } from '../src/components/ProductTable';
import { catalog } from './fixtures';
const products = [catalog.products[0], { ...catalog.products[0], id: 2, name: 'Test Keyboard', sku: 'KEY-002', category: 'Accessories' }];
describe('visible catalogue search', () => {
  it('filters by name, SKU or category while ignoring case and outer spaces', () => {
    render(<ProductTable products={products} onDetails={vi.fn()} />);
    const search = screen.getByRole('searchbox', { name: 'Search products' });
    for (const value of [' wireless mouse ', 'mouse-001', 'ELECTRONICS']) {
      fireEvent.change(search, { target: { value } });
      expect(screen.getByText('Wireless Mouse')).toBeInTheDocument();
      expect(screen.queryByText('Test Keyboard')).not.toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent('Showing 1 of 2 loaded products');
    }
  });
  it('shows no matches and restores products with Clear search', () => {
    render(<ProductTable products={products} onDetails={vi.fn()} />);
    const search = screen.getByRole('searchbox', { name: 'Search products' });
    fireEvent.change(search, { target: { value: 'missing product' } });
    expect(screen.getByText('No products match your search.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(search).toHaveValue('');
    expect(screen.getByText('Wireless Mouse')).toBeInTheDocument();
    expect(screen.getByText('Test Keyboard')).toBeInTheDocument();
  });
});
