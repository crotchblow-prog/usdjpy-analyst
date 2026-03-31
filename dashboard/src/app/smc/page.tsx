"use client";

import { useEffect, useState } from "react";
import { supabase, Report, Scenario, Zone, LiquidityLevel } from "@/lib/supabase";
import { useLocale } from "@/lib/providers";
import { Card, CardHeader } from "@/components/Card";
import { DirectionBadge, GradeBadge } from "@/components/Badge";
import { StaleIndicator } from "@/components/StaleIndicator";
import type { TranslationKey } from "@/lib/i18n";

export default function SMCPage() {
  const { t } = useLocale();
  const [report, setReport] = useState<Report | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [levels, setLevels] = useState<LiquidityLevel[]>([]);
  const [loading, setLoading] = useState(true);
  const [nearbyOnly, setNearbyOnly] = useState(true);

  useEffect(() => {
    async function load() {
      const res = await supabase
        .from("reports")
        .select("*")
        .eq("report_type", "smc")
        .order("date", { ascending: false })
        .limit(1)
        .single();

      if (res.data) {
        setReport(res.data);
        const [scRes, zRes, lRes] = await Promise.all([
          supabase.from("scenarios").select("*").eq("report_id", res.data.id),
          supabase.from("zones").select("*").eq("report_id", res.data.id).order("zone_high", { ascending: false }),
          supabase.from("liquidity_levels").select("*").eq("report_id", res.data.id).order("price", { ascending: false }),
        ]);
        if (scRes.data) setScenarios(scRes.data);
        if (zRes.data) setZones(zRes.data);
        if (lRes.data) setLevels(lRes.data);
      }
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-40 bg-bg-secondary rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex items-center justify-center h-64 text-text-muted">
        {t("smc.noData")}
      </div>
    );
  }

  const filteredZones = nearbyOnly ? zones.filter((z) => z.is_nearby) : zones;
  const groupedZones = groupByTimeframe(filteredZones);

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      {/* Header */}
      <StaleIndicator timestamp={report.generation_time || report.created_at} />
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">{t("smc.title")}</h1>
        <span className="text-sm text-text-muted">{report.date}</span>
        <DirectionBadge direction={report.direction} />
        <GradeBadge grade={report.grade} />
      </div>

      {/* Entry Plan */}
      {report.entry_price && (
        <Card>
          <CardHeader>{t("smc.entryPlan")}</CardHeader>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 text-sm">
            <div>
              <span className="text-text-muted">{t("dashboard.setupType")}</span>
              <div className="font-medium">{report.setup_type}</div>
            </div>
            <div>
              <span className="text-text-muted">{t("dashboard.entry")}</span>
              <div className="font-mono font-medium">{report.entry_price?.toFixed(2)}</div>
            </div>
            <div>
              <span className="text-text-muted">{t("dashboard.stop")}</span>
              <div className="font-mono font-medium text-bear">{report.stop_price?.toFixed(2)}</div>
            </div>
            <div>
              <span className="text-text-muted">{t("dashboard.target1")}</span>
              <div className="font-mono font-medium text-bull">{report.target1_price?.toFixed(2)}</div>
            </div>
            <div>
              <span className="text-text-muted">{t("dashboard.target2")}</span>
              <div className="font-mono font-medium text-bull">{report.target2_price?.toFixed(2) ?? "-"}</div>
            </div>
          </div>
        </Card>
      )}

      {/* Scenarios */}
      {scenarios.length > 0 && (
        <Card>
          <CardHeader>{t("smc.scenarios")}</CardHeader>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {scenarios.map((sc) => (
              <ScenarioCard key={sc.id} scenario={sc} t={t} />
            ))}
          </div>
        </Card>
      )}

      {/* Playbook Chart */}
      {report.playbook_chart_url && (
        <Card>
          <CardHeader>Playbook Chart</CardHeader>
          <img
            src={report.playbook_chart_url}
            alt="12h Playbook Chart"
            className="w-full max-w-none rounded-lg"
          />
        </Card>
      )}

      {/* Active Zones */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <CardHeader className="mb-0">{t("smc.zones")}</CardHeader>
          <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={nearbyOnly}
              onChange={(e) => setNearbyOnly(e.target.checked)}
              className="rounded"
            />
            {t("smc.nearby")}
          </label>
        </div>
        <div className="overflow-x-auto">
          {Object.entries(groupedZones).map(([tf, tfZones]) => (
            <div key={tf} className="mb-4 last:mb-0">
              <h4 className="text-xs font-bold text-text-muted mb-1.5 font-mono">{tf}</h4>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-text-muted text-left">
                    <th className="pb-1 font-medium">{t("smc.type")}</th>
                    <th className="pb-1 font-medium">{t("smc.zone")}</th>
                    <th className="pb-1 font-medium">{t("smc.status")}</th>
                    <th className="pb-1 font-medium text-right">{t("smc.distance")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {tfZones.map((z) => (
                    <tr key={z.id} className="hover:bg-bg-card-hover transition-colors">
                      <td className="py-1">
                        <span
                          className={`${
                            z.direction === "Long" ? "text-bull" : "text-bear"
                          } ${z.is_intervention ? "font-bold" : ""}`}
                        >
                          {z.zone_type}
                          {z.is_intervention ? " *" : ""}
                        </span>
                      </td>
                      <td className="py-1 font-mono">
                        {z.zone_low.toFixed(2)}-{z.zone_high.toFixed(2)}
                      </td>
                      <td className="py-1 text-text-secondary">{z.status}</td>
                      <td className="py-1 text-right text-text-muted">
                        {z.distance_pips != null ? `${z.distance_pips}p` : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {filteredZones.length === 0 && (
            <p className="text-sm text-text-muted py-4 text-center">
              {nearbyOnly ? "No zones within 100 pips" : "No zones data"}
            </p>
          )}
        </div>
      </Card>

      {/* Liquidity Levels */}
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
                      <LevelTypeBadge type={lv.level_type} />
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

function ScenarioCard({ scenario, t }: { scenario: Scenario; t: (k: TranslationKey) => string }) {
  const typeLabels: Record<string, string> = {
    primary: t("smc.primary"),
    alternative: t("smc.alternative"),
    tail_risk: t("smc.tailRisk"),
  };
  const typeBg: Record<string, string> = {
    primary: "border-bull/40 bg-bull/5",
    alternative: "border-intervention/40 bg-intervention/5",
    tail_risk: "border-bear/40 bg-bear/5",
  };

  return (
    <div className={`rounded-lg border p-3 ${typeBg[scenario.scenario_type] ?? "border-border"}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold uppercase text-text-muted">
          {typeLabels[scenario.scenario_type] ?? scenario.scenario_type}
        </span>
        <span className="text-sm font-bold">{scenario.probability}%</span>
      </div>
      <h4 className="text-sm font-semibold mb-2">{scenario.name}</h4>
      <div className="space-y-1 text-xs text-text-secondary">
        {scenario.key_level && (
          <div>
            <span className="text-text-muted">{t("smc.keyLevel")}:</span>{" "}
            <span className="font-mono">{scenario.key_level.toFixed(2)}</span>
          </div>
        )}
        {scenario.trigger_description && (
          <div>
            <span className="text-text-muted">{t("smc.trigger")}:</span> {scenario.trigger_description}
          </div>
        )}
        {scenario.action && (
          <div>
            <span className="text-text-muted">{t("smc.action")}:</span> {scenario.action}
          </div>
        )}
        {scenario.invalidation && (
          <div>
            <span className="text-text-muted">{t("smc.invalidation")}:</span> {scenario.invalidation}
          </div>
        )}
      </div>
      {(scenario.session1_name || scenario.session2_name) && (
        <div className="mt-2 pt-2 border-t border-border/50 space-y-1 text-xs">
          {scenario.session1_name && (
            <div>
              <span className="font-semibold">{scenario.session1_name}:</span>{" "}
              <span className="text-text-secondary">{scenario.session1_description}</span>
            </div>
          )}
          {scenario.session2_name && (
            <div>
              <span className="font-semibold">{scenario.session2_name}:</span>{" "}
              <span className="text-text-secondary">{scenario.session2_description}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LevelTypeBadge({ type }: { type: string }) {
  const colorClass =
    type === "INTERVENTION"
      ? "bg-intervention/15 text-intervention"
      : type.includes("EQH")
        ? "bg-bull/10 text-bull"
        : type.includes("EQL")
          ? "bg-bear/10 text-bear"
          : "bg-bg-secondary text-text-secondary";

  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${colorClass}`}>{type}</span>
  );
}

function groupByTimeframe(zones: Zone[]): Record<string, Zone[]> {
  const grouped: Record<string, Zone[]> = {};
  for (const z of zones) {
    if (!grouped[z.timeframe]) grouped[z.timeframe] = [];
    grouped[z.timeframe].push(z);
  }
  return grouped;
}
