import type { Money, Product } from "../types";

export function grossMargin(price: Money, cost: Money | null): number | null {
  const sale = Number(price), productCost = Number(cost);
  if (cost === null || !Number.isFinite(sale) || !Number.isFinite(productCost) || sale <= 0 || productCost < 0) return null;
  return ((sale - productCost) / sale) * 100;
}

export function previousMargin(product: Product): number | null {
  const latest = [...product.price_history].sort((a, b) => Date.parse(b.changed_at) - Date.parse(a.changed_at))[0];
  return latest ? grossMargin(latest.old_price, product.cost_price) : null;
}

export function marginSeries(product: Product, limit = 6): { label: string; value: number }[] {
  if (product.cost_price === null) return [];
  const history = [...product.price_history].sort((a, b) => Date.parse(a.changed_at) - Date.parse(b.changed_at));
  const points = history.flatMap(record => {
    const value = grossMargin(record.new_price, product.cost_price);
    return value === null ? [] : [{ label: new Date(record.changed_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }), value }];
  });
  const current = grossMargin(product.selling_price, product.cost_price);
  if (current !== null) points.push({ label: "Now", value: current });
  return points.slice(-limit);
}

export function marginStatus(value: number | null): "Cost required" | "At risk" | "Watch" | "Healthy" {
  if (value === null) return "Cost required";
  if (value < 10) return "At risk";
  if (value < 25) return "Watch";
  return "Healthy";
}
