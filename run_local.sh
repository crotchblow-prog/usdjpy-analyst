#!/bin/bash
# USD/JPY Analysis — Local cron runner
# Usage: run_local.sh <job_type>
#   job_type: morning | afternoon | monitor | scorecard | validation

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

export TZ=Asia/Tokyo
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Source env vars not available in cron
[ -f "$HOME/.zshrc" ] && source <(grep -E '^export (SUPABASE_SERVICE_ROLE_KEY|USDJPY_EMAIL_PASSWORD)=' "$HOME/.zshrc") 2>/dev/null || true

PYTHON=/usr/local/bin/python3
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR" data/raw output/daily output/weekly output/scorecard

DATE=$(date +%Y-%m-%d)
DOW=$(date +%u)  # 1=Mon ... 7=Sun
JOB="${1:-}"
LOG="$LOG_DIR/cron_${JOB}_${DATE}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" | tee -a "$LOG"; }

log "=== Starting job: $JOB ==="

case "$JOB" in
  morning)
    log "Running daily report..."
    $PYTHON run_daily_analysis.py >> "$LOG" 2>&1 || log "WARN: daily report failed"

    REPORT="output/daily/${DATE}.md"
    if [ -f "$REPORT" ]; then
      log "Generating PDF..."
      $PYTHON scripts/generate_pdf.py "$REPORT" >> "$LOG" 2>&1 || log "WARN: PDF generation failed"
      log "Pushing daily to Supabase..."
      $PYTHON scripts/push_to_supabase.py "$REPORT" >> "$LOG" 2>&1 || log "WARN: Supabase push failed"
    fi

    # Weekly on Mondays
    if [ "$DOW" -eq 1 ]; then
      log "Running weekly report (Monday)..."
      $PYTHON run_daily_analysis.py --weekly >> "$LOG" 2>&1 || log "WARN: weekly report failed"
      WREPORT="output/weekly/${DATE}.md"
      if [ -f "$WREPORT" ]; then
        $PYTHON scripts/generate_pdf.py "$WREPORT" >> "$LOG" 2>&1 || true
        $PYTHON scripts/push_to_supabase.py "$WREPORT" >> "$LOG" 2>&1 || true
      fi
    fi

    log "Running SMC analysis..."
    $PYTHON scripts/run_smc_analysis.py --mode full >> "$LOG" 2>&1 || log "WARN: SMC analysis failed"
    ;;

  afternoon)
    log "Running afternoon SMC analysis..."
    $PYTHON scripts/run_smc_analysis.py --mode full >> "$LOG" 2>&1 || log "WARN: SMC analysis failed"
    ;;

  monitor)
    log "Running scenario monitor..."
    $PYTHON scripts/run_scenario_monitor.py --mode check >> "$LOG" 2>&1 || log "WARN: monitor failed"
    ;;

  scorecard)
    log "Running scorecard..."
    $PYTHON scripts/run_scenario_monitor.py --mode scorecard >> "$LOG" 2>&1 || log "WARN: scorecard failed"
    ;;

  validation)
    log "Running validation..."
    $PYTHON scripts/run_validation.py >> "$LOG" 2>&1 || log "WARN: validation failed"
    ;;

  *)
    log "ERROR: Unknown job type: $JOB"
    log "Usage: run_local.sh {morning|afternoon|monitor|scorecard|validation}"
    exit 1
    ;;
esac

log "=== Done: $JOB ==="
