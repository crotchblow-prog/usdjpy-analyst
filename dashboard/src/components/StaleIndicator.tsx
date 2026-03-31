"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/lib/providers";

export function StaleIndicator({ timestamp }: { timestamp: string | null }) {
  const { t } = useLocale();
  const [hoursAgo, setHoursAgo] = useState<number | null>(null);

  useEffect(() => {
    if (!timestamp) return;
    const update = () => {
      const diff = Date.now() - new Date(timestamp).getTime();
      setHoursAgo(diff / (1000 * 60 * 60));
    };
    update();
    const interval = setInterval(update, 60000); // update every minute
    return () => clearInterval(interval);
  }, [timestamp]);

  if (hoursAgo === null || !timestamp) return null;

  const isStale = hoursAgo > 4;
  const formattedTime = new Date(timestamp).toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const agoText =
    hoursAgo < 1
      ? `${Math.round(hoursAgo * 60)}${t("stale.mAgo")}`
      : hoursAgo < 24
        ? `${Math.round(hoursAgo)}${t("stale.hAgo")}`
        : `${Math.round(hoursAgo / 24)}${t("stale.dAgo")}`;

  return (
    <div
      className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg ${
        isStale
          ? "bg-intervention/10 text-intervention border border-intervention/20"
          : "text-text-muted"
      }`}
    >
      {isStale && <span>{"\u26A0"}</span>}
      <span>
        {t("common.lastUpdated")}: {formattedTime} JST ({agoText})
      </span>
      {isStale && (
        <span className="font-medium">— {t("stale.warning")}</span>
      )}
    </div>
  );
}
