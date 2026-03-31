"use client";

import { useEffect, useState } from "react";
import { supabase, JournalEntry } from "@/lib/supabase";
import { useLocale } from "@/lib/providers";
import { Card, CardHeader } from "@/components/Card";
import { DirectionBadge, GradeBadge } from "@/components/Badge";

export default function JournalPage() {
  const { t } = useLocale();
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const res = await supabase
        .from("journal_entries")
        .select("*")
        .order("date_open", { ascending: false })
        .limit(100);

      if (res.data) setEntries(res.data);
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

  // Compute stats
  const closed = entries.filter((e) => e.exit_price != null);
  const wins = closed.filter((e) => (e.pips ?? 0) > 0);
  const winRate = closed.length > 0 ? Math.round((wins.length / closed.length) * 100) : 0;
  const totalPips = closed.reduce((s, e) => s + (e.pips ?? 0), 0);
  const totalPnl = closed.reduce((s, e) => s + (e.pnl ?? 0), 0);

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <h1 className="text-xl font-bold">{t("journal.title")}</h1>

      {entries.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-text-muted">
          {t("journal.noData")}
        </div>
      ) : (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Trades" value={entries.length.toString()} />
            <StatCard label="Win Rate" value={`${winRate}%`} color={winRate >= 50 ? "text-bull" : "text-bear"} />
            <StatCard
              label="Total Pips"
              value={`${totalPips >= 0 ? "+" : ""}${totalPips.toFixed(1)}`}
              color={totalPips >= 0 ? "text-bull" : "text-bear"}
            />
            <StatCard
              label="Total P&L"
              value={`$${totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}`}
              color={totalPnl >= 0 ? "text-bull" : "text-bear"}
            />
          </div>

          {/* Trade list */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted text-left text-xs">
                    <th className="pb-2 font-medium">{t("journal.ticket")}</th>
                    <th className="pb-2 font-medium">{t("journal.date")}</th>
                    <th className="pb-2 font-medium">{t("journal.direction")}</th>
                    <th className="pb-2 font-medium">{t("journal.lots")}</th>
                    <th className="pb-2 font-medium">{t("journal.entryPrice")}</th>
                    <th className="pb-2 font-medium">{t("journal.exitPrice")}</th>
                    <th className="pb-2 font-medium text-right">{t("journal.pips")}</th>
                    <th className="pb-2 font-medium text-right">{t("journal.pnl")}</th>
                    <th className="pb-2 font-medium">{t("journal.grade")}</th>
                    <th className="pb-2 font-medium">{t("journal.setup")}</th>
                    <th className="pb-2 font-medium">{t("journal.biasAligned")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {entries.map((e) => {
                    const isOpen = e.exit_price == null;
                    return (
                      <tr key={e.id} className="hover:bg-bg-card-hover transition-colors">
                        <td className="py-2 font-mono text-xs">{e.ticket}</td>
                        <td className="py-2 text-xs">
                          {e.date_open
                            ? new Date(e.date_open).toLocaleDateString("ja-JP", { timeZone: "Asia/Tokyo" })
                            : "-"}
                        </td>
                        <td className="py-2">
                          <DirectionBadge direction={e.direction} />
                        </td>
                        <td className="py-2 font-mono text-xs">{e.lots ?? "-"}</td>
                        <td className="py-2 font-mono text-xs">{e.entry_price?.toFixed(3) ?? "-"}</td>
                        <td className="py-2 font-mono text-xs">
                          {isOpen ? (
                            <span className="text-intervention text-xs">{t("journal.open")}</span>
                          ) : (
                            e.exit_price?.toFixed(3)
                          )}
                        </td>
                        <td className={`py-2 text-right font-mono text-xs ${
                          (e.pips ?? 0) >= 0 ? "text-bull" : "text-bear"
                        }`}>
                          {e.pips != null ? `${e.pips >= 0 ? "+" : ""}${e.pips.toFixed(1)}` : "-"}
                        </td>
                        <td className={`py-2 text-right font-mono text-xs ${
                          (e.pnl ?? 0) >= 0 ? "text-bull" : "text-bear"
                        }`}>
                          {e.pnl != null ? `${e.pnl >= 0 ? "+" : ""}${e.pnl.toFixed(2)}` : "-"}
                        </td>
                        <td className="py-2">
                          <GradeBadge grade={e.grade} />
                        </td>
                        <td className="py-2 text-xs text-text-secondary">{e.setup_type ?? "-"}</td>
                        <td className="py-2">
                          {e.bias_aligned === true ? (
                            <span className="text-bull text-xs">Yes</span>
                          ) : e.bias_aligned === false ? (
                            <span className="text-bear text-xs">No</span>
                          ) : (
                            <span className="text-text-muted text-xs">-</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
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
