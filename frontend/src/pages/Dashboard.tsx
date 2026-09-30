import React, { useEffect, useState } from "react";
import { DollarSign, ShoppingCart, Package, Sparkles, RefreshCw } from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { HealthBadge } from "../components/HealthBadge";
import { HealthStatus } from "../types";

export const Dashboard: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus>({ status: "loading" });
  const [lastChecked, setLastChecked] = useState<string>("");

  const checkHealth = async () => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/v1/health/detailed`);
      if (res.ok) {
        const data = await res.json();
        setHealth(data);
      } else {
        // Fallback to basic /health
        const basicRes = await fetch(`${apiUrl}/health`);
        if (basicRes.ok) {
          setHealth({ status: "ok" });
        } else {
          setHealth({ status: "error" });
        }
      }
    } catch {
      setHealth({ status: "error" });
    } finally {
      setLastChecked(new Date().toLocaleTimeString());
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-sky-600 flex items-center justify-center text-white font-bold text-lg shadow-sm">
              CP
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-900 leading-tight">
                CartPilot
              </h1>
              <span className="text-xs font-medium text-sky-600 uppercase tracking-wider">
                AI Manager
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <HealthBadge health={health} />
            <button
              onClick={checkHealth}
              title="Refresh Health"
              className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {/* Subheader */}
        <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">Storefront Overview</h2>
            <p className="text-sm text-slate-500 mt-1">
              Phase 1 Foundation • Operating Loop: Sense → Decide → Act → Learn
            </p>
          </div>
          {lastChecked && (
            <div className="text-xs text-slate-400">
              Last synced: {lastChecked}
            </div>
          )}
        </div>

        {/* 4 Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard
            title="Revenue"
            value="$124,500"
            change="+14.2%"
            changeType="positive"
            caption="vs last month"
            icon={<DollarSign className="w-5 h-5 text-emerald-600" />}
          />

          <MetricCard
            title="Orders"
            value="1,420"
            change="+8.5%"
            changeType="positive"
            caption="today"
            icon={<ShoppingCart className="w-5 h-5 text-sky-600" />}
          />

          <MetricCard
            title="Inventory"
            value="3,850"
            change="4 low stock"
            changeType="negative"
            caption="across 20 SKUs"
            icon={<Package className="w-5 h-5 text-amber-600" />}
          />

          <MetricCard
            title="AI Recommendations"
            value="3 Pending"
            change="2 pricing, 1 restock"
            changeType="neutral"
            caption="awaiting merchant review"
            icon={<Sparkles className="w-5 h-5 text-indigo-600" />}
          />
        </div>

        {/* System Diagnostics Card */}
        <div className="mt-8 bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h3 className="text-base font-semibold text-slate-900 mb-4">
            Phase 1 Infrastructure Diagnostics
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-xs font-semibold uppercase text-slate-500 block mb-1">
                FastAPI Backend
              </span>
              <span className="font-medium text-slate-900">
                {health.status === "ok" || health.status === "degraded" ? "Operational (Port 8000)" : "Waiting for Server"}
              </span>
            </div>
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-xs font-semibold uppercase text-slate-500 block mb-1">
                PostgreSQL
              </span>
              <span className="font-medium text-slate-900">
                {health.database === "connected" ? "Connected" : "Standby (Phase 1 Ready)"}
              </span>
            </div>
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-xs font-semibold uppercase text-slate-500 block mb-1">
                Redis
              </span>
              <span className="font-medium text-slate-900">
                {health.redis === "connected" ? "Connected" : "Standby (Phase 1 Ready)"}
              </span>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-xs text-slate-500">
          CartPilot • Multi-Agent E-Commerce Management Platform • MVP Phase 1
        </div>
      </footer>
    </div>
  );
};
