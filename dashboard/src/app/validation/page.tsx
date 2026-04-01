"use client";

import { useEffect, useState } from "react";
import { supabase, type ValidationResult } from "@/lib/supabase";
import { useLocale } from "@/lib/providers";
import { Card, CardHeader } from "@/components/Card";
import type { TranslationKey } from "@/lib/i18n";

const MODULE_NAMES: Record<string, TranslationKey> = {
  "01": "validation.module01",
  "03": "validation.module03",
  "05": "validation.module05",
  "07": "validation.module07",
  "08": "validation.module08",
  "module_01": "validation.module01",
  "module_03": "validation.module03",
  "module_05": "validation.module05",
  "module_07": "validation.module07",
  "module_08": "validation.module08",
};

const INDICATOR_LABELS: Record<string, string> = {
  spot_usdjpy: "USD/JPY Spot",
  spot_dxy: "DXY",
  us_10y: "US 10Y Yield",
  jp_10y: "JP 10Y Yield",
  rate_spread: "Rate Spread",
  rsi_14: "RSI (14)",
  sma_50: "SMA 50",
  sma_200: "SMA 200",
  macd_line: "MACD Line",
  macd_signal: "MACD Signal",
  ichimoku_tenkan: "Ichimoku Tenkan",
  ichimoku_kijun: "Ichimoku Kijun",
  spot_sp500: "S&P 500",
  spot_nikkei: "Nikkei 225",
  spot_gold: "Gold",
  spot_vix: "VIX",
  spot_wti: "WTI Oil",
};

function formatIndicator(key: string): string {
  return INDICATOR_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    PASS: "bg-bull/20 text-bull",
    WARN: "bg-yellow-500/20 text-yellow-400",
    FAIL: "bg-bear/20 text-bear",
    SKIP: "bg-text-muted/20 text-text-muted",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-mono font-medium ${colors[status] || ""}`}
    >
      {status}
    </span>
  );
}

function statusRank(status: string): number {
  return { FAIL: 0, WARN: 1, PASS: 2, SKIP: 3 }[status] ?? 4;
}

function worstStatus(results: ValidationResult[]): string {
  return results.reduce((worst, r) => {
    return statusRank(r.status) < statusRank(worst) ? r.status : worst;
  }, "SKIP");
}

interface ModuleGroup {
  module: string;
  results: ValidationResult[];
}

export default function ValidationPage() {
  const { t } = useLocale();
  const [results, setResults] = useState<ValidationResult[]>([]);
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  // Fetch available dates on mount
  useEffect(() => {
    async function loadDates() {
      const res = await supabase
        .from("validation")
        .select("date")
        .order("date", { ascending: false })
        .limit(30);

      if (res.data) {
        const unique = [...new Set(res.data.map((r: { date: string }) => r.date))];
        setDates(unique);
        if (unique.length > 0) setSelectedDate(unique[0]);
      }
      setLoading(false);
    }
    loadDates();
  }, []);

  // Fetch results whenever selectedDate changes
  useEffect(() => {
    if (!selectedDate) return;
    setLoading(true);
    async function loadResults() {
      const res = await supabase
        .from("validation")
        .select("*")
        .eq("date", selectedDate)
        .order("module")
        .order("indicator");

      if (res.data) setResults(res.data as ValidationResult[]);
      setLoading(false);
    }
    loadResults();
  }, [selectedDate]);

  function toggleModule(module: string) {
    setExpandedModules((prev) => {
      const next = new Set(prev);
      if (next.has(module)) {
        next.delete(module);
      } else {
        next.add(module);
      }
      return next;
    });
  }

  // Compute summary stats
  const nonSkip = results.filter((r) => r.status !== "SKIP");
  const passed = nonSkip.filter((r) => r.status === "PASS").length;
  const total = nonSkip.length;
  const passRate = total > 0 ? Math.round((passed / total) * 100) : 0;
  const passRateColor =
    passRate >= 90 ? "text-bull" : passRate >= 75 ? "text-yellow-400" : "text-bear";

  // Last checked timestamp (guard against null checked_at)
  const lastChecked = (() => {
    const withTimestamp = results.filter((r) => r.checked_at);
    if (withTimestamp.length === 0) return null;
    const latest = withTimestamp.reduce((a, b) =>
      a.checked_at > b.checked_at ? a : b
    );
    return new Date(latest.checked_at).toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
    });
  })();

  // Status counts for summary
  const warnCount = results.filter((r) => r.status === "WARN").length;
  const failCount = results.filter((r) => r.status === "FAIL").length;
  const skipCount = results.filter((r) => r.status === "SKIP").length;

  // Group by module
  const moduleGroups: ModuleGroup[] = Object.entries(
    results.reduce<Record<string, ValidationResult[]>>((acc, r) => {
      if (!acc[r.module]) acc[r.module] = [];
      acc[r.module].push(r);
      return acc;
    }, {})
  )
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([module, moduleResults]) => ({ module, moduleResults: moduleResults } as unknown as ModuleGroup))
    .map(({ module }) => ({
      module,
      results: results.filter((r) => r.module === module),
    }));

  if (loading && dates.length === 0) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-20 bg-bg-secondary rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      {/* Page header + date selector */}
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold">{t("validation.title")}</h1>
        {dates.length > 0 && (
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="text-sm rounded-lg border border-border bg-bg-card text-text-primary px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-border"
          >
            {dates.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-16 bg-bg-secondary rounded-xl animate-pulse" />
          ))}
        </div>
      ) : results.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-text-muted">
          {t("validation.noData")}
        </div>
      ) : (
        <>
          {/* Summary Card */}
          <Card>
            <CardHeader>{t("validation.summary")}</CardHeader>
            <div className="flex items-center gap-6 flex-wrap">
              <div>
                <p className="text-xs text-text-muted mb-1">{t("validation.passRate")}</p>
                <p className={`text-3xl font-bold font-mono ${passRateColor}`}>
                  {passed}/{total}
                </p>
                <p className={`text-sm font-mono ${passRateColor}`}>{passRate}%</p>
              </div>
              <div className="flex gap-3">
                <div className="text-center">
                  <StatusBadge status="PASS" />
                  <p className="text-sm font-mono mt-1">{passed}</p>
                </div>
                <div className="text-center">
                  <StatusBadge status="WARN" />
                  <p className="text-sm font-mono mt-1">{warnCount}</p>
                </div>
                <div className="text-center">
                  <StatusBadge status="FAIL" />
                  <p className="text-sm font-mono mt-1">{failCount}</p>
                </div>
                <div className="text-center">
                  <StatusBadge status="SKIP" />
                  <p className="text-sm font-mono mt-1">{skipCount}</p>
                </div>
              </div>
              {lastChecked && (
                <div>
                  <p className="text-xs text-text-muted mb-1">{t("validation.lastChecked")}</p>
                  <p className="text-sm font-mono text-text-secondary">{lastChecked}</p>
                </div>
              )}
            </div>
          </Card>

          {/* Module Breakdown */}
          <div className="space-y-2">
            {moduleGroups.map(({ module, results: moduleResults }) => {
              const moduleNonSkip = moduleResults.filter((r) => r.status !== "SKIP");
              const modulePassed = moduleNonSkip.filter((r) => r.status === "PASS").length;
              const moduleTotal = moduleNonSkip.length;
              const worst = worstStatus(moduleResults);
              const nameKey = MODULE_NAMES[module];
              const moduleName = nameKey ? t(nameKey) : `Module ${module}`;
              const isExpanded = expandedModules.has(module);

              return (
                <Card key={module} className="p-0 overflow-hidden">
                  {/* Module row — clickable */}
                  <button
                    onClick={() => toggleModule(module)}
                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-bg-card-hover transition-colors text-left"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs text-text-muted w-6">M{module.replace("module_", "")}</span>
                      <span className="text-sm font-medium text-text-primary">{moduleName}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-mono text-text-secondary">
                        {modulePassed}/{moduleTotal}
                      </span>
                      <StatusBadge status={worst} />
                      <svg
                        className={`w-4 h-4 text-text-muted transition-transform ${isExpanded ? "rotate-180" : ""}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>
                  </button>

                  {/* Expanded indicator detail */}
                  {isExpanded && (
                    <div className="border-t border-border overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-text-muted text-left bg-bg-secondary">
                            <th className="px-4 py-2 font-medium">{t("validation.indicator")}</th>
                            <th className="px-4 py-2 font-medium text-right">{t("validation.ourValue")}</th>
                            <th className="px-4 py-2 font-medium">{t("validation.source")}</th>
                            <th className="px-4 py-2 font-medium text-right">{t("validation.sourceValue")}</th>
                            <th className="px-4 py-2 font-medium text-right">{t("validation.diff")}</th>
                            <th className="px-4 py-2 font-medium text-right">{t("validation.tolerance")}</th>
                            <th className="px-4 py-2 font-medium text-center">{t("validation.status")}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {moduleResults.map((r) => (
                            <tr
                              key={r.id}
                              className={
                                r.status === "FAIL"
                                  ? "bg-bear/5"
                                  : r.status === "WARN"
                                  ? "bg-yellow-500/5"
                                  : ""
                              }
                            >
                              <td className="px-4 py-2 font-mono text-text-primary">{formatIndicator(r.indicator)}</td>
                              <td className="px-4 py-2 font-mono text-right text-text-secondary">
                                {r.our_value != null ? r.our_value.toFixed(4) : "-"}
                              </td>
                              <td className="px-4 py-2 text-text-secondary">{r.source_name}</td>
                              <td className="px-4 py-2 font-mono text-right text-text-secondary">
                                {r.source_value != null ? r.source_value.toFixed(4) : "-"}
                              </td>
                              <td className="px-4 py-2 font-mono text-right text-text-secondary">
                                {r.diff != null ? r.diff.toFixed(4) : "-"}
                              </td>
                              <td className="px-4 py-2 font-mono text-right text-text-muted">
                                {r.tolerance != null ? r.tolerance.toFixed(4) : "-"}
                              </td>
                              <td className="px-4 py-2 text-center">
                                <StatusBadge status={r.status} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
