"use client";

import { useEffect, useState, useCallback } from "react";
import { supabase, Report } from "@/lib/supabase";
import { useLocale } from "@/lib/providers";
import { Card, CardHeader } from "@/components/Card";
import { DirectionBadge, ConfidenceBadge } from "@/components/Badge";
import { StaleIndicator } from "@/components/StaleIndicator";
import type { TranslationKey } from "@/lib/i18n";

// ── Module data types ─────────────────────────────────────────────────
interface Module01 {
  us_10y: number;
  jp_10y: number;
  spread: number;
  spread_trend: string;
  divergence: string;
  spread_1w_chg?: number;
  spread_1m_chg?: number;
  signal: string;
  confidence: string;
}

interface Module02 {
  signal: string;
  confidence: string;
  boj_rate: string;
  boj_stance: string;
  boj_last_meeting: string;
  boj_next_meeting: string;
  boj_key_quote: string;
  fed_rate: string;
  fed_stance: string;
  fed_last_meeting: string;
  fed_next_meeting: string;
  fed_key_quote: string;
  intervention_risk: string;
  last_intervention: string;
  political_risk: string;
  political_development: string;
}

interface Module03 {
  price: number;
  rsi: number;
  sma50: number;
  sma200: number;
  sma_cross: string;
  macd_signal: string;
  ichimoku: string;
  signal: string;
  confidence: string;
}

interface Module04 {
  signal: string;
  confidence: string;
  net_position: number;
  wow_change: number;
  percentile: number;
  crowded: boolean;
  crowded_direction: string;
}

interface Module05 {
  correlations: Record<string, number>;
  breakdowns: string[];
  regime: string;
  signal: string;
  confidence: string;
}

interface Module06 {
  signal: string;
  confidence: string;
  seasonal_bias: string;
  fy_position: string;
  repatriation: string;
  upcoming_events: Array<{ date: string; event: string; impact: string }>;
  trade_balance: string;
}

interface ChecklistSignal {
  module: string;
  name: string;
  direction: string;
  confidence: string;
  note: string;
}

interface Module07 {
  direction: string;
  confidence: string;
  score: number;
  max_score: number;
  modules_active: number;
  modules_total: number;
  conviction_capped: boolean;
  signals: ChecklistSignal[];
}

interface ModuleData {
  module_01?: Module01;
  module_02?: Module02;
  module_03?: Module03;
  module_04?: Module04;
  module_05?: Module05;
  module_06?: Module06;
  module_07?: Module07;
}

// Expected correlation directions for breakdown detection
const EXPECTED_CORR: Record<string, string> = {
  sp500: "Positive",
  nikkei: "Positive",
  gold: "Negative",
  vix: "Negative",
  oil: "Positive",
};

export default function DailyPage() {
  const { locale, t } = useLocale();
  const [report, setReport] = useState<Report | null>(null);
  const [dates, setDates] = useState<string[]>([]);
  const [dateIndex, setDateIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"daily" | "weekly">("daily");

  // Load available dates for the active tab
  useEffect(() => {
    async function loadDates() {
      const res = await supabase
        .from("reports")
        .select("date")
        .eq("report_type", activeTab)
        .order("date", { ascending: false })
        .limit(60);
      if (res.data) {
        const unique = [...new Set(res.data.map((r: { date: string }) => r.date))];
        setDates(unique);
        setDateIndex(0);
      }
    }
    loadDates();
  }, [activeTab]);

  // Load report for selected date
  const loadReport = useCallback(
    async (date?: string) => {
      setLoading(true);
      let query = supabase
        .from("reports")
        .select("*")
        .eq("report_type", activeTab)
        .order("date", { ascending: false });

      if (date) {
        query = query.eq("date", date);
      }

      const res = await query.limit(1).single();
      if (res.data) {
        setReport(res.data);
      } else {
        setReport(null);
      }
      setLoading(false);
    },
    [activeTab]
  );

  useEffect(() => {
    if (dates.length > 0) {
      loadReport(dates[dateIndex]);
    } else {
      loadReport();
    }
  }, [dateIndex, dates, loadReport]);

  const goNext = () => {
    if (dateIndex > 0) setDateIndex(dateIndex - 1);
  };
  const goPrev = () => {
    if (dateIndex < dates.length - 1) setDateIndex(dateIndex + 1);
  };

  if (loading) return <LoadingSkeleton />;

  if (!report) {
    return (
      <div className="max-w-6xl mx-auto space-y-4">
        {/* Tab switcher even when no data */}
        <TabSwitcher activeTab={activeTab} setActiveTab={setActiveTab} t={t} />
        <div className="flex items-center justify-center h-64 text-text-muted">
          {t("daily.noData")}
        </div>
      </div>
    );
  }

  const moduleData = (report.module_data ?? {}) as ModuleData;
  const m01 = moduleData.module_01;
  const m02 = moduleData.module_02;
  const m03 = moduleData.module_03;
  const m04 = moduleData.module_04;
  const m05 = moduleData.module_05;
  const m06 = moduleData.module_06;
  const m07 = moduleData.module_07;

  const riskAlerts: string[] = Array.isArray(report.risk_alerts)
    ? report.risk_alerts
    : typeof report.risk_alerts === "string"
      ? JSON.parse(report.risk_alerts)
      : [];

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      {/* Header */}
      <StaleIndicator timestamp={report.generation_time || report.created_at} />

      <div className="flex flex-wrap items-center gap-3">
        {/* Date selector */}
        <div className="flex items-center gap-1">
          <button
            onClick={goPrev}
            disabled={dateIndex >= dates.length - 1}
            className="px-2 py-1 rounded text-sm text-text-secondary hover:bg-bg-card-hover disabled:opacity-30 disabled:cursor-not-allowed"
          >
            &larr;
          </button>
          <span className="text-sm font-mono font-medium text-text-primary min-w-[7rem] text-center">
            {report.date}
          </span>
          <button
            onClick={goNext}
            disabled={dateIndex <= 0}
            className="px-2 py-1 rounded text-sm text-text-secondary hover:bg-bg-card-hover disabled:opacity-30 disabled:cursor-not-allowed"
          >
            &rarr;
          </button>
        </div>

        <h1 className="text-xl font-bold">
          {activeTab === "weekly" ? t("daily.weeklyTitle") : t("daily.title")}
        </h1>
      </div>

      {/* Tab switcher */}
      <TabSwitcher activeTab={activeTab} setActiveTab={setActiveTab} t={t} />

      {/* ── Module 07: Checklist ──────────────────────────────────── */}
      {m07 ? (
        <Card>
          <CardHeader>{t("daily.checklist")}</CardHeader>

          {/* Direction + score bar */}
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <DirectionBadge direction={m07.direction} />
            <ConfidenceBadge confidence={m07.confidence} />
            <ScoreBar score={m07.score} maxScore={m07.max_score} />
          </div>

          {/* Conviction capped warning */}
          {m07.conviction_capped && (
            <div className="text-xs bg-intervention/10 text-intervention border border-intervention/20 rounded-lg px-3 py-1.5 mb-3">
              {m07.modules_active}/{m07.modules_total} {t("daily.convictionCapped")}
            </div>
          )}

          {/* Signal grid */}
          {m07.signals && m07.signals.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted text-left">
                    <th className="pb-2 font-medium">{t("daily.module")}</th>
                    <th className="pb-2 font-medium">{t("daily.signal")}</th>
                    <th className="pb-2 font-medium">Direction</th>
                    <th className="pb-2 font-medium text-right">{t("daily.score")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {m07.signals.map((sig, i) => {
                    const isNA = sig.direction === "N/A";
                    const isBull = sig.direction === "BULL";
                    const isBear = sig.direction === "BEAR";
                    const score = isBull ? 1 : isBear ? -1 : 0;
                    const dirColor = isBull ? "text-bull" : isBear ? "text-bear" : "text-text-muted";
                    const dirLabel = isNA ? "---"
                      : isBull ? t("structure.BULLISH")
                      : isBear ? t("structure.BEARISH")
                      : t("direction.NEUTRAL");

                    return (
                      <tr key={i} className={`transition-colors ${isNA ? "opacity-40" : "hover:bg-bg-card-hover"}`}>
                        <td className="py-1.5 text-text-secondary">
                          <span className="font-mono text-text-muted">{sig.module}</span>{" "}
                          {sig.name}
                        </td>
                        <td className="py-1.5 text-text-secondary text-xs">
                          {isNA ? (
                            activeTab === "daily" ? (
                              <button
                                onClick={() => setActiveTab("weekly")}
                                className="text-text-muted italic hover:text-bull hover:underline cursor-pointer transition-colors"
                              >
                                {t("daily.availableInWeekly")}
                              </button>
                            ) : (
                              <span className="text-text-muted italic">{sig.note}</span>
                            )
                          ) : sig.note}
                        </td>
                        <td className={`py-1.5 font-bold text-xs ${dirColor}`}>
                          {dirLabel}
                        </td>
                        <td className="py-1.5 text-right font-mono font-bold">
                          {isNA ? (
                            <span className="text-text-muted">---</span>
                          ) : (
                            <span className={score > 0 ? "text-bull" : score < 0 ? "text-bear" : "text-text-muted"}>
                              {score > 0 ? `+${score}` : score}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      ) : null}

      {/* ── Module 01: Macro Regime ──────────────────────────────── */}
      {m01 && (
        <Card>
          <CardHeader>{t("daily.macroRegime")}</CardHeader>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4">
            <MetricBox label="US 10Y" value={`${m01.us_10y.toFixed(2)}%`} />
            <MetricBox label="JP 10Y" value={`${m01.jp_10y.toFixed(2)}%`} />
            <MetricBox
              label={t("daily.spread")}
              value={`${m01.spread.toFixed(2)}%`}
              sub={
                m01.spread_trend === "WIDENING"
                  ? t("daily.widening")
                  : t("daily.narrowing")
              }
              subColor={m01.spread_trend === "WIDENING" ? "text-bull" : "text-bear"}
            />
            <MetricBox
              label={t("daily.divergence")}
              value={m01.divergence === "CONFIRMED" ? t("daily.confirmed") : m01.divergence}
              valueColor={m01.divergence === "CONFIRMED" ? "text-bull" : "text-text-muted"}
            />
          </div>

          {/* Spread changes */}
          {(m01.spread_1w_chg != null || m01.spread_1m_chg != null) && (
            <div className="flex gap-4 text-xs text-text-muted mb-4">
              {m01.spread_1w_chg != null && (
                <span>
                  1W: <span className={m01.spread_1w_chg >= 0 ? "text-bull" : "text-bear"}>
                    {m01.spread_1w_chg >= 0 ? "+" : ""}{m01.spread_1w_chg.toFixed(2)}%
                  </span>
                </span>
              )}
              {m01.spread_1m_chg != null && (
                <span>
                  1M: <span className={m01.spread_1m_chg >= 0 ? "text-bull" : "text-bear"}>
                    {m01.spread_1m_chg >= 0 ? "+" : ""}{m01.spread_1m_chg.toFixed(2)}%
                  </span>
                </span>
              )}
            </div>
          )}

          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-text-muted">{t("daily.signal")}:</span>
            <SignalLabel signal={m01.signal} />
            <ConfidenceBadge confidence={m01.confidence} />
          </div>

          {report.macro_chart_url && (
            <img
              src={report.macro_chart_url}
              alt="Macro Spread Chart"
              className="w-full max-w-none rounded-lg"
            />
          )}
        </Card>
      )}

      {/* ── Module 02: Policy & Politics ─────────────────────────── */}
      {m02 && (
        <Card>
          <CardHeader>{t("daily.policy")}</CardHeader>

          {/* BOJ + Fed side by side */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* BOJ */}
            <div className="bg-bg-secondary rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="font-bold text-sm">BOJ</span>
                <StanceBadge stance={m02.boj_stance} />
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-muted">Rate</span>
                  <span className="font-mono font-medium">{m02.boj_rate}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Last Meeting</span>
                  <span className="font-mono text-xs">{m02.boj_last_meeting}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Next Meeting</span>
                  <span className="font-mono text-xs">{m02.boj_next_meeting}</span>
                </div>
                {m02.boj_key_quote && (
                  <div className="mt-2 text-xs text-text-secondary italic border-l-2 border-border pl-2">
                    {m02.boj_key_quote}
                  </div>
                )}
              </div>
            </div>

            {/* Fed */}
            <div className="bg-bg-secondary rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="font-bold text-sm">Fed</span>
                <StanceBadge stance={m02.fed_stance} />
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-muted">Rate</span>
                  <span className="font-mono font-medium">{m02.fed_rate}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Last Meeting</span>
                  <span className="font-mono text-xs">{m02.fed_last_meeting}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Next Meeting</span>
                  <span className="font-mono text-xs">{m02.fed_next_meeting}</span>
                </div>
                {m02.fed_key_quote && (
                  <div className="mt-2 text-xs text-text-secondary italic border-l-2 border-border pl-2">
                    {m02.fed_key_quote}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Intervention Risk */}
          <div className="mb-4">
            <span className="text-xs text-text-muted mb-1 block">{t("daily.interventionRisk")}</span>
            <InterventionRiskBar risk={m02.intervention_risk} />
            {m02.last_intervention && (
              <span className="text-xs text-text-muted mt-1 block">
                Last intervention: {m02.last_intervention}
              </span>
            )}
          </div>

          {/* Political developments */}
          {m02.political_development && (
            <div className="mb-4">
              <span className="text-xs text-text-muted mb-1 block">Political Developments</span>
              <p className="text-sm text-text-secondary">{m02.political_development}</p>
              {m02.political_risk && (
                <span className="text-xs text-text-muted mt-1 block">
                  Risk: {m02.political_risk}
                </span>
              )}
            </div>
          )}

          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">{t("daily.signal")}:</span>
            <SignalLabel signal={m02.signal} />
            <ConfidenceBadge confidence={m02.confidence} />
          </div>
        </Card>
      )}

      {/* ── Module 03: Technicals ────────────────────────────────── */}
      {m03 && (
        <Card>
          <CardHeader>{t("daily.technicals")}</CardHeader>

          {/* Indicator strip */}
          <div className="flex flex-wrap gap-2 mb-4">
            <IndicatorChip
              label="RSI"
              value={m03.rsi?.toFixed(1) ?? "—"}
              status={m03.rsi != null ? (m03.rsi > 70 ? "overbought" : m03.rsi < 30 ? "oversold" : "neutral") : "neutral"}
            />
            <IndicatorChip
              label="SMA Cross"
              value={m03.sma_cross}
              status={m03.sma_cross === "GOLDEN" ? "bull" : m03.sma_cross === "DEATH" ? "bear" : "neutral"}
            />
            <IndicatorChip
              label="MACD"
              value={m03.macd_signal}
              status={m03.macd_signal === "BULLISH" ? "bull" : m03.macd_signal === "BEARISH" ? "bear" : "neutral"}
            />
            <IndicatorChip
              label="Ichimoku"
              value={m03.ichimoku}
              status={m03.ichimoku === "ABOVE" ? "bull" : m03.ichimoku === "BELOW" ? "bear" : "neutral"}
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4">
            {m03.price != null && <MetricBox label="Price" value={m03.price.toFixed(2)} />}
            <MetricBox label="SMA 50" value={m03.sma50?.toFixed(2) ?? "—"} />
            <MetricBox label="SMA 200" value={m03.sma200?.toFixed(2) ?? "—"} />
            <MetricBox label="RSI" value={m03.rsi?.toFixed(1) ?? "—"} />
          </div>

          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-text-muted">{t("daily.signal")}:</span>
            <SignalLabel signal={m03.signal} />
            <ConfidenceBadge confidence={m03.confidence} />
          </div>

          {report.technicals_chart_url && (
            <img
              src={report.technicals_chart_url}
              alt="Technicals Chart"
              className="w-full max-w-none rounded-lg"
            />
          )}
        </Card>
      )}

      {/* ── Module 04: Positioning (COT) ─────────────────────────── */}
      {m04 && (
        <Card>
          <CardHeader>{t("daily.positioning")}</CardHeader>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            {/* Net position big number */}
            <div className="sm:col-span-1">
              <span className="text-xs text-text-muted block mb-1">{t("daily.netPosition")}</span>
              <div className="text-2xl font-bold font-mono">
                <span className={m04.net_position < 0 ? "text-bear" : "text-bull"}>
                  {m04.net_position < 0 ? "\u25BC" : "\u25B2"}{" "}
                  {Math.abs(m04.net_position).toLocaleString()}
                </span>
              </div>
              <span className="text-xs text-text-muted">{t("daily.contracts")}</span>
            </div>

            {/* WoW change */}
            <div>
              <span className="text-xs text-text-muted block mb-1">WoW Change</span>
              <div className="font-mono font-medium">
                <span className={m04.wow_change >= 0 ? "text-bull" : "text-bear"}>
                  {m04.wow_change >= 0 ? "+" : ""}{m04.wow_change.toLocaleString()}
                </span>
              </div>
            </div>

            {/* Crowded badge */}
            <div>
              <span className="text-xs text-text-muted block mb-1">Percentile</span>
              <div className="font-mono font-medium">
                {m04.percentile?.toFixed(0) ?? "—"}%
                {m04.crowded && (
                  <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-bear/15 text-bear font-bold">
                    {t("daily.crowded")}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Percentile gauge */}
          <div className="mb-4">
            <PercentileGauge percentile={m04.percentile} crowded={m04.crowded} />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">{t("daily.signal")}:</span>
            <SignalLabel signal={m04.signal} />
            <ConfidenceBadge confidence={m04.confidence} />
          </div>
        </Card>
      )}

      {/* ── Module 05: Cross-Asset ───────────────────────────────── */}
      {m05 && (
        <Card>
          <CardHeader>{t("daily.crossAsset")}</CardHeader>

          <div className="overflow-x-auto mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-muted text-left">
                  <th className="pb-2 font-medium">Asset</th>
                  <th className="pb-2 font-medium">Correlation</th>
                  <th className="pb-2 font-medium">Expected</th>
                  <th className="pb-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {Object.entries(m05.correlations).map(([asset, corr]) => {
                  const expected = EXPECTED_CORR[asset] ?? "Positive";
                  const isPositive = corr >= 0;
                  const matchesExpected =
                    (expected === "Positive" && isPositive) ||
                    (expected === "Negative" && !isPositive);
                  const isBreakdown = m05.breakdowns?.includes(asset);

                  return (
                    <tr
                      key={asset}
                      className={`hover:bg-bg-card-hover transition-colors ${
                        isBreakdown ? "bg-intervention/5" : ""
                      }`}
                    >
                      <td className="py-1.5 font-medium capitalize">{asset}</td>
                      <td className="py-1.5 font-mono">
                        <span className={corr >= 0 ? "text-bull" : "text-bear"}>
                          {corr >= 0 ? "+" : ""}{corr.toFixed(3)}
                        </span>
                      </td>
                      <td className="py-1.5 text-text-muted">{expected}</td>
                      <td className="py-1.5">
                        {isBreakdown ? (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-intervention/15 text-intervention font-bold">
                            BREAKDOWN
                          </span>
                        ) : matchesExpected ? (
                          <span className="text-xs text-text-muted">OK</span>
                        ) : (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-bear/10 text-bear">
                            DIVERGENT
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-text-muted">Regime:</span>
            <span className="text-xs font-bold text-text-secondary">{m05.regime}</span>
            <span className="text-xs text-text-muted ml-2">{t("daily.signal")}:</span>
            <SignalLabel signal={m05.signal} />
            <ConfidenceBadge confidence={m05.confidence} />
          </div>

          {report.correlations_chart_url && (
            <img
              src={report.correlations_chart_url}
              alt="Correlations Chart"
              className="w-full max-w-none rounded-lg"
            />
          )}
        </Card>
      )}

      {/* ── Module 06: Seasonality ───────────────────────────────── */}
      {m06 && (
        <Card>
          <CardHeader>{t("daily.seasonality")}</CardHeader>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm mb-4">
            <MetricBox label="Seasonal Bias" value={m06.seasonal_bias} />
            <MetricBox label={t("daily.fyEnd")} value={m06.fy_position} />
            <MetricBox label={t("daily.repatriation")} value={m06.repatriation} />
          </div>

          {/* Upcoming events table */}
          {m06.upcoming_events && m06.upcoming_events.length > 0 && (
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted text-left">
                    <th className="pb-2 font-medium">Date</th>
                    <th className="pb-2 font-medium">Event</th>
                    <th className="pb-2 font-medium">Impact</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {m06.upcoming_events.map((evt, i) => (
                    <tr key={i} className="hover:bg-bg-card-hover transition-colors">
                      <td className="py-1.5 font-mono text-xs">{evt.date}</td>
                      <td className="py-1.5 text-text-secondary">{evt.event}</td>
                      <td className="py-1.5">
                        <span
                          className={`text-xs font-bold ${
                            evt.impact === "HIGH"
                              ? "text-bear"
                              : evt.impact === "MED"
                                ? "text-intervention"
                                : "text-text-muted"
                          }`}
                        >
                          {evt.impact}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {m06.trade_balance && (
            <div className="text-sm text-text-secondary mb-4">
              Trade Balance: {m06.trade_balance}
            </div>
          )}

          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">{t("daily.signal")}:</span>
            <SignalLabel signal={m06.signal} />
            <ConfidenceBadge confidence={m06.confidence} />
          </div>
        </Card>
      )}

      {/* ── Risk Alerts ──────────────────────────────────────────── */}
      {riskAlerts.length > 0 && (
        <Card>
          <CardHeader>{t("daily.riskAlerts")}</CardHeader>
          <ul className="space-y-1.5">
            {riskAlerts.map((alert, i) => {
              const isElevated = alert.includes("ELEVATED") || alert.includes("CRITICAL");
              return (
                <li key={i} className="text-sm flex items-start gap-2">
                  <span
                    className={`mt-0.5 text-xs ${
                      isElevated ? "text-bear" : "text-intervention"
                    }`}
                  >
                    {isElevated ? "\u26A0" : "\u25CF"}
                  </span>
                  <span className="text-text-secondary">{alert}</span>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {/* ── Bottom Line ──────────────────────────────────────────── */}
      {report.recommendation && (
        <Card>
          <CardHeader>{t("daily.bottomLine")}</CardHeader>
          <p className="text-sm text-text-secondary leading-relaxed">
            {report.recommendation}
          </p>
        </Card>
      )}
    </div>
  );
}

// ── Helper Components ─────────────────────────────────────────────────

function TabSwitcher({
  activeTab,
  setActiveTab,
  t,
}: {
  activeTab: "daily" | "weekly";
  setActiveTab: (tab: "daily" | "weekly") => void;
  t: (key: TranslationKey) => string;
}) {
  return (
    <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
      <button
        onClick={() => setActiveTab("daily")}
        className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
          activeTab === "daily"
            ? "bg-bull text-white"
            : "bg-bg-secondary text-text-secondary hover:text-text-primary"
        }`}
      >
        {t("daily.tabDaily")}
      </button>
      <button
        onClick={() => setActiveTab("weekly")}
        className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
          activeTab === "weekly"
            ? "bg-bull text-white"
            : "bg-bg-secondary text-text-secondary hover:text-text-primary"
        }`}
      >
        {t("daily.tabWeekly")}
      </button>
    </div>
  );
}

function StanceBadge({ stance }: { stance: string }) {
  const upper = stance.toUpperCase();
  const isHawkish = upper.includes("HAWKISH");
  const isDovish = upper.includes("DOVISH");

  const colorClass = isHawkish
    ? "bg-bear/10 text-bear"
    : isDovish
      ? "bg-bull/10 text-bull"
      : "bg-bg-secondary text-text-secondary";

  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded ${colorClass}`}>
      {stance}
    </span>
  );
}

function InterventionRiskBar({ risk }: { risk: string }) {
  const upper = risk.toUpperCase();
  const level =
    upper.includes("CRITICAL") ? 3
    : upper.includes("STRONG") || upper.includes("ELEVATED") ? 2
    : 1; // LOW

  return (
    <div className="flex items-center gap-2">
      <div className="flex h-2 w-full max-w-xs rounded-full overflow-hidden">
        <div
          className={`flex-1 ${level >= 1 ? "bg-bull" : "bg-bg-secondary"}`}
        />
        <div
          className={`flex-1 ${level >= 2 ? "bg-intervention" : "bg-bg-secondary"}`}
        />
        <div
          className={`flex-1 ${level >= 3 ? "bg-bear" : "bg-bg-secondary"}`}
        />
      </div>
      <span
        className={`text-xs font-bold ${
          level >= 3 ? "text-bear" : level >= 2 ? "text-intervention" : "text-bull"
        }`}
      >
        {risk}
      </span>
    </div>
  );
}

function PercentileGauge({ percentile, crowded }: { percentile: number; crowded: boolean }) {
  const clampedPct = Math.max(0, Math.min(100, percentile));

  return (
    <div className="relative w-full max-w-md">
      <div className="flex justify-between text-xs text-text-muted mb-1">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
      <div className="relative h-2 bg-bg-secondary rounded-full overflow-visible">
        {/* Crowded zones */}
        <div className="absolute left-0 top-0 h-full w-[15%] bg-bear/20 rounded-l-full" />
        <div className="absolute right-0 top-0 h-full w-[15%] bg-bear/20 rounded-r-full" />
        {/* Position marker */}
        <div
          className={`absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-white ${
            crowded ? "bg-bear" : "bg-bull"
          }`}
          style={{ left: `calc(${clampedPct}% - 6px)` }}
        />
      </div>
    </div>
  );
}

function SignalLabel({ signal }: { signal: string }) {
  const color =
    signal === "BULLISH" || signal === "BULL"
      ? "text-bull"
      : signal === "BEARISH" || signal === "BEAR"
        ? "text-bear"
        : "text-text-muted";
  return <span className={`text-xs font-bold ${color}`}>{signal}</span>;
}

function ScoreBar({ score, maxScore }: { score: number; maxScore: number }) {
  const pct = maxScore > 0 ? Math.abs(score) / maxScore : 0;
  const barColor = score > 0 ? "bg-bull" : score < 0 ? "bg-bear" : "bg-neutral";

  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-sm font-bold">
        {score > 0 ? "+" : ""}{score}/{maxScore > 0 ? `+${maxScore}` : maxScore}
      </span>
      <div className="w-24 h-2 bg-bg-secondary rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  );
}

function MetricBox({
  label,
  value,
  sub,
  subColor,
  valueColor,
}: {
  label: string;
  value: string;
  sub?: string;
  subColor?: string;
  valueColor?: string;
}) {
  return (
    <div>
      <span className="text-text-muted text-xs">{label}</span>
      <div className={`font-mono font-medium ${valueColor ?? "text-text-primary"}`}>
        {value}
      </div>
      {sub && (
        <span className={`text-xs ${subColor ?? "text-text-muted"}`}>{sub}</span>
      )}
    </div>
  );
}

function IndicatorChip({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: "bull" | "bear" | "neutral" | "overbought" | "oversold";
}) {
  const colorClass =
    status === "bull"
      ? "bg-bull/10 text-bull border-bull/20"
      : status === "bear" || status === "overbought"
        ? "bg-bear/10 text-bear border-bear/20"
        : status === "oversold"
          ? "bg-intervention/10 text-intervention border-intervention/20"
          : "bg-bg-secondary text-text-secondary border-border";

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${colorClass}`}>
      <span className="text-text-muted">{label}:</span>
      <span className="font-bold">{value}</span>
    </span>
  );
}

function LoadingSkeleton() {
  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <div className="h-8 w-64 bg-bg-secondary rounded animate-pulse" />
      <div className="h-48 bg-bg-secondary rounded-xl animate-pulse" />
      <div className="h-40 bg-bg-secondary rounded-xl animate-pulse" />
      <div className="h-40 bg-bg-secondary rounded-xl animate-pulse" />
      <div className="h-40 bg-bg-secondary rounded-xl animate-pulse" />
    </div>
  );
}
