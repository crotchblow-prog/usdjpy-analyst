import { createClient } from "@supabase/supabase-js";

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

// ── Types matching Supabase schema ──────────────────────────────────────

export interface Report {
  id: string;
  date: string;
  report_type: "daily" | "weekly" | "smc";
  generation_time: string | null;
  direction: "LONG" | "SHORT" | "NEUTRAL";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  grade: string | null;
  setup_type: string | null;
  entry_price: number | null;
  stop_price: number | null;
  target1_price: number | null;
  target2_price: number | null;
  confluence_score: number | null;
  confirmation_status: string | null;
  current_price: number | null;
  market_structure_4h: string | null;
  market_structure_1h: string | null;
  market_structure_15m: string | null;
  market_structure_5m: string | null;
  premium_discount: string | null;
  recommendation: string | null;
  risk_alerts: string[];
  warnings: string[];
  md_content: string | null;
  playbook_chart_url: string | null;
  module_data: Record<string, unknown> | null;
  macro_chart_url: string | null;
  technicals_chart_url: string | null;
  correlations_chart_url: string | null;
  created_at: string;
}

export interface Scenario {
  id: string;
  report_id: string;
  scenario_type: "primary" | "alternative" | "tail_risk";
  name: string;
  probability: number;
  key_level: number | null;
  trigger_description: string | null;
  action: string | null;
  invalidation: string | null;
  session1_name: string | null;
  session1_description: string | null;
  session2_name: string | null;
  session2_description: string | null;
}

export interface Scorecard {
  id: string;
  report_id: string;
  window_start: string | null;
  window_end: string | null;
  actual_high: number | null;
  actual_low: number | null;
  actual_close: number | null;
  primary_outcome: string | null;
  alternative_outcome: string | null;
  tail_risk_outcome: string | null;
  best_match: string | null;
  entry_zone_hit: boolean | null;
  theoretical_pl_pips: number | null;
  mae_pips: number | null;
  mfe_pips: number | null;
}

export interface Zone {
  id: string;
  report_id: string;
  timeframe: string;
  zone_type: string;
  zone_high: number;
  zone_low: number;
  direction: string;
  status: string;
  is_intervention: boolean;
  distance_pips: number | null;
  is_nearby: boolean;
}

export interface LiquidityLevel {
  id: string;
  report_id: string;
  price: number;
  level_type: string;
  significance: string;
}

export interface JournalEntry {
  id: string;
  report_id: string | null;
  ticket: string;
  date_open: string | null;
  date_close: string | null;
  direction: "LONG" | "SHORT";
  entry_price: number | null;
  exit_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  lots: number | null;
  pips: number | null;
  pnl: number | null;
  grade: string | null;
  setup_type: string | null;
  bias_aligned: boolean | null;
  notes: string | null;
}
