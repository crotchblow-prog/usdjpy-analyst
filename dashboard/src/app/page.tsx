"use client";

import { useEffect, useState } from "react";
import { supabase, Report, LiquidityLevel } from "@/lib/supabase";
import { useLocale } from "@/lib/providers";
import { Card, CardHeader } from "@/components/Card";
import { GradeBadge } from "@/components/Badge";
import { StaleIndicator } from "@/components/StaleIndicator";
import type { TranslationKey } from "@/lib/i18n";

export default function DashboardPage() {
  const { locale, t } = useLocale();
  const [daily, setDaily] = useState<Report | null>(null);
  const [smc, setSmc] = useState<Report | null>(null);
  const [levels, setLevels] = useState<LiquidityLevel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const [dailyRes, smcRes] = await Promise.all([
        supabase
          .from("reports")
          .select("*")
          .in("report_type", ["daily", "weekly"])
          .order("date", { ascending: false })
          .limit(1)
          .single(),
        supabase
          .from("reports")
          .select("*")
          .eq("report_type", "smc")
          .order("date", { ascending: false })
          .limit(1)
          .single(),
      ]);

      if (dailyRes.data) setDaily(dailyRes.data);
      if (smcRes.data) {
        setSmc(smcRes.data);
        const levelsRes = await supabase
          .from("liquidity_levels")
          .select("*")
          .eq("report_id", smcRes.data.id)
          .order("price", { ascending: false });
        if (levelsRes.data) setLevels(levelsRes.data);
      }
      setLoading(false);
    }
    load();
  }, []);

  if (loading) return <LoadingSkeleton />;

  const report = smc || daily;
  if (!report) {
    return (
      <div className="flex items-center justify-center h-64 text-text-muted">
        {t("dashboard.noReport")}
      </div>
    );
  }

  const riskAlerts: string[] = Array.isArray(report.risk_alerts)
    ? report.risk_alerts
    : typeof report.risk_alerts === "string"
      ? JSON.parse(report.risk_alerts)
      : [];

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      {/* Stale data indicator */}
      <StaleIndicator timestamp={report.generation_time || report.created_at} />

      {/* HERO CARD */}
      <div className="rounded-xl overflow-hidden bg-[#1a1a2e] dark:bg-[#1a1a2e] text-white p-5">
        {/* Direction + Grade + Confirmation row */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <span className="text-[28px] font-bold tracking-tight">
              {report.direction === "LONG" ? (
                <><span className="text-green-400">{"\u25B2"}</span> <span>{t("direction.LONG")}</span></>
              ) : report.direction === "SHORT" ? (
                <><span className="text-red-400">{"\u25BC"}</span> <span>{t("direction.SHORT")}</span></>
              ) : (
                <><span className="text-gray-400">{"\u25C6"}</span> <span>{t("direction.NEUTRAL")}</span></>
              )}
            </span>
            {smc && (
              <span className="text-sm text-gray-400 font-medium">
                {smc.confidence === "HIGH" ? t("confidence.HIGH") : smc.confidence === "MEDIUM" ? t("confidence.MEDIUM") : t("confidence.LOW")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {smc && <GradeBadge grade={smc.grade} />}
            {smc?.confirmation_status && (
              <span
                className={`text-xs font-bold px-2 py-1 rounded ${
                  smc.confirmation_status === "CONFIRMED"
                    ? "bg-green-500/20 text-green-400"
                    : smc.confirmation_status === "PENDING"
                      ? "bg-amber-500/20 text-amber-400"
                      : "bg-gray-500/20 text-gray-400"
                }`}
              >
                {smc.confirmation_status === "CONFIRMED"
                  ? t("confirmation.CONFIRMED")
                  : smc.confirmation_status === "PENDING"
                    ? t("confirmation.PENDING")
                    : smc.confirmation_status === "NOT_ACTIVE" || smc.confirmation_status === "NOT ACTIVE"
                      ? t("confirmation.NOT_ACTIVE")
                      : smc.confirmation_status}
              </span>
            )}
          </div>
        </div>

        {/* Entry plan line */}
        {smc?.entry_price && (
          <div className="font-mono text-sm text-gray-300 mb-3">
            <span className="text-white">{t("dashboard.entry")} {smc.entry_price.toFixed(2)}</span>
            <span className="text-gray-500 mx-2">|</span>
            <span className="text-red-400">{t("dashboard.stop")} {smc.stop_price?.toFixed(2)}</span>
            <span className="text-gray-500 mx-2">|</span>
            <span className="text-green-400">T1 {smc.target1_price?.toFixed(2)}</span>
            {smc.target2_price && (
              <>
                <span className="text-gray-500 mx-2">|</span>
                <span className="text-green-400">T2 {smc.target2_price.toFixed(2)}</span>
              </>
            )}
          </div>
        )}

        {/* Setup type + confluence */}
        {smc && (
          <div className="text-xs text-gray-400">
            {smc.setup_type && <span>{smc.setup_type}</span>}
            {smc.confluence_score != null && (
              <span className="ml-3">Confluence: {smc.confluence_score}</span>
            )}
            <span className="ml-3">{report.date}</span>
          </div>
        )}

        {/* Verdict */}
        {report.recommendation && (
          <p className="text-xs text-gray-500 mt-2 border-t border-gray-700 pt-2">
            {report.recommendation}
          </p>
        )}
      </div>

      {/* Market Structure + Risk Alerts side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Market Structure */}
        {smc && (
          <Card>
            <CardHeader>{t("dashboard.marketStructure")}</CardHeader>
            <div className="space-y-1.5">
              {(["4h", "1h", "15m", "5m"] as const).map((tf) => {
                const key = `market_structure_${tf}` as keyof Report;
                const val = smc[key] as string | null;
                return (
                  <div key={tf} className="flex justify-between text-sm">
                    <span className="text-text-muted font-mono">{tf.toUpperCase()}</span>
                    <StructureBadge value={val} t={t} />
                  </div>
                );
              })}
              {smc.premium_discount && (
                <div className="flex justify-between text-sm mt-2 pt-2 border-t border-border">
                  <span className="text-text-muted">{t("dashboard.premiumDiscount")}</span>
                  <span className="font-medium text-text-primary">
                    <PremiumDiscountLabel value={smc.premium_discount} t={t} />
                  </span>
                </div>
              )}
            </div>
          </Card>
        )}

        {/* Risk Alerts */}
        <Card>
          <CardHeader>{t("dashboard.riskAlerts")}</CardHeader>
          {riskAlerts.length > 0 ? (
            <ul className="space-y-1.5">
              {riskAlerts.map((alert, i) => {
                const isElevated = alert.includes("ELEVATED") || alert.includes("CRITICAL");
                const isUnknown = alert.includes("UNKNOWN");
                return (
                  <li key={i} className="text-sm flex items-start gap-2">
                    <span className={`mt-0.5 text-xs ${isElevated ? "text-bear" : isUnknown ? "text-intervention" : "text-intervention"}`}>
                      {isElevated ? "\u26A0" : "\u25CF"}
                    </span>
                    <span className="text-text-secondary">{alert}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-text-muted">{t("dashboard.noAlerts")}</p>
          )}
        </Card>
      </div>

      {/* Key Liquidity Levels */}
      {levels.length > 0 && (
        <Card>
          <CardHeader>{t("smc.liquidity")}</CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-muted text-left">
                  <th className="pb-2 font-medium">{t("smc.price")}</th>
                  <th className="pb-2 font-medium">{t("smc.type")}</th>
                  <th className="pb-2 font-medium">{t("smc.significance")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {levels.map((lv) => (
                  <tr key={lv.id} className="hover:bg-bg-card-hover transition-colors">
                    <td className="py-1.5 font-mono font-medium">{lv.price.toFixed(2)}</td>
                    <td className="py-1.5">
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          lv.level_type === "INTERVENTION"
                            ? "bg-intervention/15 text-intervention"
                            : lv.level_type.includes("EQH")
                              ? "bg-bull/10 text-bull"
                              : lv.level_type.includes("EQL")
                                ? "bg-bear/10 text-bear"
                                : "bg-bg-secondary text-text-secondary"
                        }`}
                      >
                        {lv.level_type}
                      </span>
                    </td>
                    <td className="py-1.5 text-text-secondary">{lv.significance}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function StructureBadge({ value, t }: { value: string | null; t: (k: TranslationKey) => string }) {
  if (!value) return <span className="text-text-muted">-</span>;
  const color =
    value === "BULLISH" ? "text-bull" : value === "BEARISH" ? "text-bear" : "text-neutral";
  const label =
    value === "BULLISH" ? t("structure.BULLISH")
    : value === "BEARISH" ? t("structure.BEARISH")
    : value === "TRANSITIONAL" ? t("structure.TRANSITIONAL")
    : value;
  return <span className={`font-medium ${color}`}>{label}</span>;
}

function PremiumDiscountLabel({ value, t }: { value: string; t: (k: TranslationKey) => string }) {
  const normalized = value.replace(/_/g, " ");
  if (normalized === "DEEP PREMIUM") return <>{t("pd.DEEP_PREMIUM")}</>;
  if (normalized === "PREMIUM") return <>{t("pd.PREMIUM")}</>;
  if (normalized === "DISCOUNT") return <>{t("pd.DISCOUNT")}</>;
  return <>{normalized}</>;
}

function LoadingSkeleton() {
  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <div className="h-32 bg-bg-secondary rounded-xl animate-pulse" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="h-48 bg-bg-secondary rounded-xl animate-pulse" />
        <div className="h-48 bg-bg-secondary rounded-xl animate-pulse" />
      </div>
    </div>
  );
}
