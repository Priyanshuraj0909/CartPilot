import React from "react";
import { HealthStatus } from "../types";

interface HealthBadgeProps {
  health: HealthStatus;
}

export const HealthBadge: React.FC<HealthBadgeProps> = ({ health }) => {
  const getStatusDisplay = () => {
    switch (health.status) {
      case "ok":
        return {
          dotColor: "bg-emerald-500",
          textColor: "text-emerald-700",
          bgColor: "bg-emerald-50 border-emerald-200",
          text: "API Connected",
        };
      case "degraded":
        return {
          dotColor: "bg-amber-500",
          textColor: "text-amber-700",
          bgColor: "bg-amber-50 border-amber-200",
          text: "API Degraded",
        };
      case "loading":
        return {
          dotColor: "bg-sky-500 animate-pulse",
          textColor: "text-sky-700",
          bgColor: "bg-sky-50 border-sky-200",
          text: "Checking API...",
        };
      default:
        return {
          dotColor: "bg-rose-500",
          textColor: "text-rose-700",
          bgColor: "bg-rose-50 border-rose-200",
          text: "API Offline",
        };
    }
  };

  const current = getStatusDisplay();

  return (
    <div
      data-testid="health-badge"
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-medium ${current.bgColor} ${current.textColor}`}
    >
      <span className={`w-2 h-2 rounded-full ${current.dotColor}`} />
      <span>{current.text}</span>
    </div>
  );
};
