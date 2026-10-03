import type { ReactNode } from "react";
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  const className = /high|critical|out of stock|invalid/i.test(tone) ? "badge danger" : /medium|low stock/i.test(tone) ? "badge warning" : /healthy|low|synergy/i.test(tone) ? "badge positive" : "badge";
  return <span className={className}>{children}</span>;
}
export function ErrorAlert({ message, retry }: { message: string; retry?: () => void }) { return <div role="alert" className="alert error">{message}{retry && <button className="btn secondary" onClick={retry}>Try again</button>}</div>; }
export function EmptyState({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }
export function Loading({ text = "Loading store data…" }: { text?: string }) { return <div role="status" className="loading"><span className="spinner" />{text}</div>; }
export function PageTitle({ title, description, children }: { title: string; description: string; children?: ReactNode }) { return <div className="page-title"><div><p className="eyebrow">MERCHANT OPERATIONS</p><h1>{title}</h1><p>{description}</p></div>{children}</div>; }
