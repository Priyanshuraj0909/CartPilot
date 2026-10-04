import { describe, expect, it } from 'vitest';
import { parseSalesCsv, SALES_CSV_HEADER } from '../src/services/salesCsv';
const line = 'sale-1,1,2,1099.00,2026-10-03T10:00:00+05:30';
describe('sales CSV validation', () => {
  it('accepts BOM and Windows line endings', () => {
    expect(parseSalesCsv(`\uFEFF${SALES_CSV_HEADER}\r\n${line}\r\n`)[0]).toMatchObject({ product_id: 1, quantity: 2, unit_price: '1099.00' });
  });
  it.each([
    ['empty rows', SALES_CSV_HEADER, 'at least one'],
    ['missing header', line, 'first line'],
    ['invalid product', `${SALES_CSV_HEADER}\nsale-1,0,2,10.00,2026-10-03T10:00:00Z`, 'Product ID'],
    ['fractional quantity', `${SALES_CSV_HEADER}\nsale-1,1,1.5,10.00,2026-10-03T10:00:00Z`, 'Quantity'],
    ['currency symbol', `${SALES_CSV_HEADER}\nsale-1,1,2,₹10.00,2026-10-03T10:00:00Z`, 'price'],
    ['future date', `${SALES_CSV_HEADER}\nsale-1,1,2,10.00,2999-10-03T10:00:00Z`, 'past date'],
    ['missing timezone', `${SALES_CSV_HEADER}\nsale-1,1,2,10.00,2026-10-03T10:00:00`, 'timezone'],
    ['duplicate references', `${SALES_CSV_HEADER}\n${line}\n${line}`, 'unique reference'],
    ['too many rows', `${SALES_CSV_HEADER}\n${Array(501).fill(line).join('\n')}`, '500'],
    ['oversized text', 'x'.repeat(200001), '200 KB'],
  ])('rejects %s', (_name, csv, error) => { expect(() => parseSalesCsv(csv)).toThrow(error); });
  it('accepts the 500-row limit with unique references', () => {
    const csv = `${SALES_CSV_HEADER}\n${Array.from({ length: 500 }, (_, i) => line.replace('sale-1', `sale-${i}`)).join('\n')}`;
    expect(parseSalesCsv(csv)).toHaveLength(500);
  });
});
