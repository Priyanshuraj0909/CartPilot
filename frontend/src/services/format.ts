import type { Money } from "../types";
export const currency = import.meta.env.VITE_CURRENCY || "USD";
const formatter = new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 });
export const formatCurrency = (value: Money | null) => value === null ? "Unknown" : formatter.format(Number(value));
export const formatDate = (value: string) => new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
export const percent = (value: number) => `${Math.round(value * 100)}%`;
