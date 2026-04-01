"use client";

import { useEffect, useState } from "react";
import { supabase, Scorecard, Report } from "@/lib/supabase";
import { useLocale } from "@/lib/providers";
import { Card, CardHeader } from "@/components/Card";
import { OutcomeBadge } from "@/components/Badge";

interface ScorecardWithReport extends Scorecard {
  reports: Pick<Report, "date" | "direction" | "grade" | "setup_type"> | null;
}

export default function ScorecardPage() {
  const { t } = useLocale();
  const [scorecards, setScorecards] = useState<ScorecardWithReport[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const res = await supabase
        .from("scorecard")
        .select("*, reports(date, direction, grade, setup_type)")
        .order("date", { ascending: false })
        .limit(50);

      if (res.data) setScorecards(res.data as ScorecardWithReport[]);
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-20 bg-bg-secondary rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  // Compute summary stats
  const total = scorecards.length;
  const hits = scorecards.filter((s) => s.primary_outcome === "HIT").length;
  const partials = scorecards.filter((s) => s.primary_outcome === "PARTIAL").length;
  const entryHits = scorecards.filter((s) => s.entry_zone_hit).length;
  const avgPL =
    total > 0
      ? scorecards.reduce((sum, s) => sum + (s.theoretical_pl_pips ?? 0), 0) / total
      : 0;

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <h1 className="text-xl font-bold">{t("scorecard.title")}</h1>

      {total === 0 ? (
        <div className="flex items-center justify-center h-64 text-text-muted">
          {t("scorecard.noData")}
        </div>
      ) : (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <StatCard label="Total" value={total.toString()} />
            <StatCard label="Primary HIT" value={hits.toString()} color="text-bull" />
            <StatCard label="PARTIAL" value={partials.toString()} color="text-intervention" />
            <StatCard label="Entry Hit %" value={`${Math.round((entryHits / total) * 100)}%`} />
            <StatCard
              label="Avg P&L"
              value={`${avgPL >= 0 ? "+" : ""}${avgPL.toFixed(1)}p`}
              color={avgPL >= 0 ? "text-bull" : "text-bear"}
            />
          </div>

          {/* Scorecard table */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted text-left text-xs">
                    <th className="pb-2 font-medium">{t("scorecard.date")}</th>
                    <th className="pb-2 font-medium">{t("smc.primary")}</th>
                    <th className="pb-2 font-medium">{t("smc.alternative")}</th>
                    <th className="pb-2 font-medium">{t("smc.tailRisk")}</th>
                    <th className="pb-2 font-medium">{t("scorecard.bestMatch")}</th>
                    <th className="pb-2 font-medium">{t("scorecard.entryHit")}</th>
                    <th className="pb-2 font-medium text-right">{t("scorecard.plPips")}</th>
                    <th className="pb-2 font-medium text-right">{t("scorecard.mae")}</th>
                    <th className="pb-2 font-medium text-right">{t("scorecard.mfe")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {scorecards.map((sc) => (
                    <tr key={sc.id} className="hover:bg-bg-card-hover transition-colors">
                      <td className="py-2 font-mono text-xs">{sc.date ?? sc.reports?.date ?? "-"}</td>
                      <td className="py-2"><OutcomeBadge outcome={sc.primary_outcome} /></td>
                      <td className="py-2"><OutcomeBadge outcome={sc.alternative_outcome} /></td>
                      <td className="py-2"><OutcomeBadge outcome={sc.tail_risk_outcome} /></td>
                      <td className="py-2 text-xs">{sc.best_match ?? "-"}</td>
                      <td className="py-2">
                        {sc.entry_zone_hit ? (
                          <span className="text-bull text-xs font-medium">{t("common.yes")}</span>
                        ) : (
                          <span className="text-text-muted text-xs">{t("common.no")}</span>
                        )}
                      </td>
                      <td className={`py-2 text-right font-mono text-xs ${
                        (sc.theoretical_pl_pips ?? 0) >= 0 ? "text-bull" : "text-bear"
                      }`}>
                        {sc.theoretical_pl_pips != null
                          ? `${sc.theoretical_pl_pips >= 0 ? "+" : ""}${sc.theoretical_pl_pips.toFixed(1)}`
                          : "-"}
                      </td>
                      <td className="py-2 text-right font-mono text-xs text-bear">
                        {sc.mae_pips != null ? sc.mae_pips.toFixed(1) : "-"}
                      </td>
                      <td className="py-2 text-right font-mono text-xs text-bull">
                        {sc.mfe_pips != null ? sc.mfe_pips.toFixed(1) : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color = "text-text-primary",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <Card>
      <p className="text-xs text-text-muted mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
    </Card>
  );
}
