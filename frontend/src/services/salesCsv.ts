export const SALES_CSV_HEADER = 'reference,product_id,quantity,unit_price,ordered_at';
export const MAX_CSV_BYTES = 200000;
export type SaleRow = { reference: string; product_id: number; quantity: number; unit_price: string; ordered_at: string };

export function parseSalesCsv(text: string): SaleRow[] {
  if (new TextEncoder().encode(text).length > MAX_CSV_BYTES) throw new Error('CSV must be under 200 KB.');
  const lines = text.replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  if (lines.shift()?.trim() !== SALES_CSV_HEADER) throw new Error(`The first line must be: ${SALES_CSV_HEADER}`);
  if (!lines.length || (lines.length === 1 && !lines[0].trim())) throw new Error('Add at least one sale below the header.');
  if (lines.length > 500) throw new Error('Import at most 500 sales at a time.');
  const references = new Set<string>();
  return lines.map((line, index) => {
    const fail = (message: string): never => { throw new Error(`Row ${index + 2}: ${message}`); };
    const cells = line.split(',').map(cell => cell.trim());
    if (cells.length !== 5) return fail('Use five comma-separated fields. Quoted commas are not supported.');
    const [reference, productId, quantityText, unit_price, ordered_at] = cells;
    if (!/^[A-Za-z0-9_-]{1,60}$/.test(reference)) return fail('Use a reference containing letters, numbers, hyphens or underscores.');
    if (references.has(reference)) return fail('Each sale in this upload needs a unique reference.');
    references.add(reference);
    const product_id = Number(productId), quantity = Number(quantityText);
    if (!/^\d+$/.test(productId) || !Number.isSafeInteger(product_id) || product_id <= 0) return fail('Product ID must be a positive whole number.');
    if (!/^\d+$/.test(quantityText) || !Number.isSafeInteger(quantity) || quantity < 1 || quantity > 100000) return fail('Quantity must be a whole number between 1 and 100000.');
    if (!/^\d{1,8}(\.\d{1,2})?$/.test(unit_price)) return fail('Use a price such as 1099.00, without a currency symbol or thousands separators.');
    if (Number(unit_price) * quantity > 99999999.99) return fail('The sale total exceeds the supported amount.');
    const time = new Date(ordered_at).getTime();
    if (!/(Z|[+-]\d{2}:\d{2})$/.test(ordered_at) || !Number.isFinite(time) || time > Date.now()) return fail('Use a past date with a timezone, such as 2026-10-03T10:00:00+05:30.');
    return { reference, product_id, quantity, unit_price, ordered_at };
  });
}
