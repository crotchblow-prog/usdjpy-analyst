#!/bin/bash
# =============================================================================
# USD/JPY Weekly Report Runner
# =============================================================================
# Runs all 7 modules for a comprehensive weekly analysis.
#
# Schedule with cron (10:00 AM JST, Fridays only):
#   0 10 * * 5 ~/usdjpy-analyst/run_weekly.sh >> ~/usdjpy-analyst/logs/cron.log 2>&1
# =============================================================================

set -euo pipefail

PROJECT_DIR="$HOME/usdjpy-analyst"
LOG_DIR="$PROJECT_DIR/logs"
OUTPUT_DIR="$PROJECT_DIR/output/weekly"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/run_weekly_${TODAY}.log"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

echo "========================================" | tee -a "$LOG_FILE"
echo "USD/JPY Weekly Run — $TODAY $(date +%H:%M:%S)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

if ! command -v claude &> /dev/null; then
    echo "ERROR: Claude Code CLI not found." | tee -a "$LOG_FILE"
    exit 1
fi

cd "$PROJECT_DIR"

claude -p . \
  --allowedTools "Bash(read_only:false),Read,Write,Edit" \
  --max-turns 80 \
  "Read the CLAUDE.md and all skill files under ./skills/usdjpy/. \
   Then execute the /usdjpy-weekly workflow — run ALL modules 01 through 07: \
   1. Read config.yaml for API keys and settings \
   2. Run Module 01 (Macro): fetch 12 months of FRED data, compute spread trends \
   3. Run Module 02 (Central Bank): summarize latest BOJ/Fed policy (search web if needed) \
   4. Run Module 03 (Technicals): full technical analysis with indicators \
   5. Run Module 04 (Positioning): fetch latest CFTC COT data for JPY futures \
   6. Run Module 05 (Cross-Asset): compute all correlations \
   7. Run Module 06 (Seasonality): check current seasonal bias and upcoming events \
   8. Run Module 07 (Checklist): full checklist with all 6 module inputs \
   9. Save the complete report as ./output/weekly/${TODAY}.md \
   10. Save charts as PNG in ./output/weekly/ \
   If any module is marked as not yet implemented, do your best with available data \
   and note limitations in the report." \
  2>&1 | tee -a "$LOG_FILE"

# Find report
REPORT=""
if [ -f "$OUTPUT_DIR/${TODAY}.md" ]; then
    REPORT="$OUTPUT_DIR/${TODAY}.md"
else
    REPORT=$(ls -t "$OUTPUT_DIR"/*.md 2>/dev/null | head -1)
fi

if [ -z "$REPORT" ] || [ ! -f "$REPORT" ]; then
    echo "ERROR: No weekly report found." | tee -a "$LOG_FILE"
    exit 1
fi

CHARTS=$(ls "$OUTPUT_DIR"/*"${TODAY}"*.png 2>/dev/null || true)

# Send email with [WEEKLY] tag in subject
if [ -n "${USDJPY_EMAIL_PASSWORD:-}" ]; then
    echo "Sending weekly report email..." | tee -a "$LOG_FILE"
    python3 "$PROJECT_DIR/send_report.py" "$REPORT" $CHARTS 2>&1 | tee -a "$LOG_FILE"
fi

echo "Weekly run complete. $(date +%H:%M:%S)" | tee -a "$LOG_FILE"
