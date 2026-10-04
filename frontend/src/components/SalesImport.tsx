import { useId, useRef, useState, type ClipboardEvent, type DragEvent } from 'react';
import type { Product } from '../types';
import { request } from '../services/api';
import { formatCurrency } from '../services/format';
import { MAX_CSV_BYTES, parseSalesCsv, SALES_CSV_HEADER, type SaleRow } from '../services/salesCsv';

export function SalesImport({ products, onImported }: { products: Product[]; onImported: () => void }) {
  const [text, setText] = useState('');
  const [rows, setRows] = useState<SaleRow[] | null>(null);
  const [source, setSource] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [exampleTime] = useState(() => Date.now() - 86400000);
  const generation = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const fileInputId = useId();
  const selected = products.find(p => String(p.id) === selectedId) ?? products[0];
  const example = selected ? `${SALES_CSV_HEADER}\ntest-${selected.id}-${exampleTime}-1,${selected.id},2,${selected.selling_price},${new Date(exampleTime).toISOString()}\ntest-${selected.id}-${exampleTime}-2,${selected.id},1,${selected.selling_price},${new Date(exampleTime + 3600000).toISOString()}\n` : '';

  function preview(value: string, name: string) {
    setRows(null); setError(''); setMessage(''); setSource(name);
    try { setRows(parseSalesCsv(value)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not read this CSV.'); }
  }
  async function chooseFiles(files: File[]) {
    if (busy || reading) return;
    const current = ++generation.current;
    setRows(null); setError(''); setMessage('');
    if (files.length !== 1) { setError(files.length ? 'Choose one CSV file at a time.' : 'Drag an actual CSV file from Finder or your file manager, rather than its name or a link.'); return; }
    const file = files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('Choose a .csv file. Excel workbooks must be saved as CSV first.'); return; }
    if (file.size > MAX_CSV_BYTES) { setError('File must be under 200 KB.'); return; }
    setSource(file.name); setReading(true);
    try {
      const value = typeof file.text === 'function' ? await file.text() : await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Unreadable file'));
        reader.onerror = () => reject(new Error('Unreadable file'));
        reader.onabort = () => reject(new Error('File read cancelled'));
        reader.readAsText(file);
      });
      if (generation.current !== current) return;
      setText(value); preview(value, file.name);
    } catch { if (generation.current === current) setError('Could not read the file. Choose it again.'); }
    finally { if (generation.current === current) setReading(false); }
  }
  function transferFiles(data: DataTransfer) {
    const files = Array.from(data.files);
    if (files.length) return files;
    return Array.from(data.items ?? []).filter(item => item.kind === 'file').map(item => item.getAsFile()).filter((file): file is File => file !== null);
  }
  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); event.stopPropagation(); setDragging(false);
    void chooseFiles(transferFiles(event.dataTransfer));
  }
  function paste(event: ClipboardEvent<HTMLDivElement>) {
    const files = transferFiles(event.clipboardData);
    if (files.length) { event.preventDefault(); void chooseFiles(files); }
  }
  async function importSales() {
    if (!rows || busy || reading) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await request<{ imported: number; skipped: number }>('/api/v1/sales/import', undefined, { sales: rows });
      setMessage(`${result.imported} sales imported; ${result.skipped} matching records skipped. Your revenue summary will refresh.`);
      onImported();
    } catch (e) { setError(e instanceof Error ? e.message : 'Sales import failed. Please try again.'); }
    finally { setBusy(false); }
  }
  return <section className="sales-import" aria-labelledby="sales-import-title">
    <h3 id="sales-import-title">Import sales data</h3>
    <p>Choose a CSV, drag it here, or paste its contents. Check the preview, then click Import sales.</p>
    <div className={`sales-dropzone${dragging ? ' dragging' : ''}`} role="group" aria-label="Drop or paste a sales CSV" tabIndex={0}
      onPaste={paste} onDragEnter={event => { event.preventDefault(); if (!busy && !reading) setDragging(true); }}
      onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = busy || reading ? 'none' : 'copy'; if (!busy && !reading) setDragging(true); }}
      onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }} onDropCapture={drop}>
      <strong>Drag and drop your CSV file here</strong>
      <p>You can also copy a file, click this box and press ⌘V on Mac or Ctrl+V on Windows. If your browser cannot paste files, use Choose File or paste the CSV text below.</p>
      <label className="sr-only" htmlFor={fileInputId}>Sales CSV</label>
      <input className="sr-only" id={fileInputId} ref={fileInput} type="file" accept=".csv,text/csv" disabled={busy || reading} onChange={event => { const files = Array.from(event.target.files ?? []); if (files.length) void chooseFiles(files); event.target.value = ''; }} />
      <button type="button" className="btn" disabled={busy || reading} onClick={() => fileInput.current?.click()}>{reading ? 'Reading file…' : 'Choose CSV file'}</button>
      {reading && <p role="status">Reading {source}…</p>}
      {rows && <p className="sales-file-ready" aria-live="polite">Ready: {source} · {rows.length} sales. Review the preview and click Import sales below.</p>}
      {error && <p role="alert" className="management-error">{error}</p>}
    </div>
    <div className="sales-text-input" onPaste={paste}>
      <label className="sales-paste">Paste CSV data<textarea value={text} rows={6} maxLength={MAX_CSV_BYTES} disabled={busy || reading} placeholder={SALES_CSV_HEADER} spellCheck={false}
        onChange={event => { setText(event.target.value); setRows(null); setError(''); setMessage(''); }} /></label>
      <button className="btn secondary" disabled={busy || reading || !text.trim()} onClick={() => preview(text, 'Pasted CSV')}>Preview pasted data</button>
    </div>
    <p className="muted">Up to 500 sales and 200 KB. Prices use your store currency. Importing sales does not deduct physical stock.</p>
    {rows && <div className="sales-preview"><h4>Preview: {source}</h4><p>{rows.length} sales · {rows.reduce((sum, row) => sum + row.quantity, 0)} units · {formatCurrency(rows.reduce((sum, row) => sum + Number(row.unit_price) * row.quantity, 0))} revenue</p>
      <div className="management-table"><table><thead><tr><th>Reference</th><th>Product ID</th><th>Quantity</th><th>Unit price</th><th>Date</th></tr></thead><tbody>{rows.slice(0, 5).map(row => <tr key={row.reference}><td>{row.reference}</td><td>{row.product_id}</td><td>{row.quantity}</td><td>{formatCurrency(row.unit_price)}</td><td>{row.ordered_at}</td></tr>)}</tbody></table></div>
      {rows.length > 5 && <p>Showing the first five sales. All {rows.length} will be submitted.</p>}
      <button className="btn" disabled={busy || reading} onClick={() => void importSales()}>{busy ? 'Importing…' : 'Import sales'}</button>
    </div>}
    <div className="sales-example">
      <h4>Try a test example</h4>
      <p>Select a product to fill in its ID and price automatically. Use a test store: importing this example records three units sold.</p>
      <label>Product for test example<select value={selected?.id ?? ''} disabled={!products.length || busy || reading} onChange={event => setSelectedId(event.target.value)}>
        {!products.length && <option value="">Add a product first</option>}{products.map(p => <option key={p.id} value={p.id}>{p.name} — ID {p.id}</option>)}
      </select></label>
      <div className="workspace-shortcuts"><button className="btn secondary" disabled={!example || busy || reading} onClick={() => { setText(example); preview(example, 'Test example'); }}>Insert test example</button>
        <a className="text-btn" download="cartpilot-sales-example.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(example || SALES_CSV_HEADER)}`}>Download sample CSV</a></div>
    </div>
    {message && <p role="status">{message}</p>}
  </section>;
}
