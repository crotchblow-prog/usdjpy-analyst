"use client";

export function DirectionBadge({ direction }: { direction: string }) {
  const colorClass =
    direction === "LONG"
      ? "bg-bull/15 text-bull border-bull/30"
      : direction === "SHORT"
        ? "bg-bear/15 text-bear border-bear/30"
        : "bg-neutral/15 text-neutral border-neutral/30";

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-bold border ${colorClass}`}
    >
      {direction === "LONG" ? "\u25B2" : direction === "SHORT" ? "\u25BC" : "\u25C6"}{" "}
      {direction}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  const colorClass =
    confidence === "HIGH"
      ? "bg-bull/10 text-bull"
      : confidence === "MEDIUM"
        ? "bg-intervention/10 text-intervention"
        : "bg-neutral/10 text-neutral";

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${colorClass}`}>
      {confidence}
    </span>
  );
}

export function GradeBadge({ grade }: { grade: string | null }) {
  if (!grade) return <span className="text-text-muted">-</span>;

  const colorClass = grade.startsWith("A")
    ? "text-grade-a"
    : grade.startsWith("B")
      ? "text-grade-b"
      : "text-grade-c";

  return (
    <span className={`text-lg font-bold ${colorClass}`}>{grade}</span>
  );
}

export function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return <span className="text-text-muted">-</span>;

  const colorClass =
    outcome === "HIT"
      ? "bg-bull/15 text-bull"
      : outcome === "PARTIAL"
        ? "bg-intervention/15 text-intervention"
        : outcome === "MISS"
          ? "bg-bear/15 text-bear"
          : "bg-neutral/15 text-neutral";

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${colorClass}`}>
      {outcome}
    </span>
  );
}
