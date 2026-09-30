import React from "react";
import { MetricCardData } from "../types";

interface MetricCardProps extends MetricCardData {
  icon?: React.ReactNode;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  change,
  changeType = "neutral",
  caption,
  icon,
}) => {
  const getBadgeColor = () => {
    switch (changeType) {
      case "positive":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "negative":
        return "bg-rose-50 text-rose-700 border-rose-200";
      default:
        return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };

  return (
    <div
      data-testid={`card-${title.toLowerCase().replace(/\s+/g, "-")}`}
      className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition-shadow duration-200 flex flex-col justify-between"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-500">{title}</span>
        {icon && (
          <div className="p-2 bg-slate-50 rounded-lg text-slate-600 border border-slate-100">
            {icon}
          </div>
        )}
      </div>

      <div className="mt-4">
        <div className="text-3xl font-bold tracking-tight text-slate-900">
          {value}
        </div>
        {(change || caption) && (
          <div className="mt-2 flex items-center gap-2">
            {change && (
              <span
                className={`inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full border ${getBadgeColor()}`}
              >
                {change}
              </span>
            )}
            {caption && (
              <span className="text-xs text-slate-500">{caption}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
