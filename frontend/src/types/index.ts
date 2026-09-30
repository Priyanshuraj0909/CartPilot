export interface HealthStatus {
  status: "ok" | "degraded" | "error" | "loading";
  app?: string;
  environment?: string;
  database?: string;
  redis?: string;
  version?: string;
}

export interface MetricCardData {
  title: string;
  value: string;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  caption?: string;
}
