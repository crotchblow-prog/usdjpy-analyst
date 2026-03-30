#!/bin/bash
# =============================================================================
# USD/JPY Daily Report Runner
# =============================================================================
# Runs Claude Code to generate a daily report, then emails it.
#
# Schedule with cron (10:00 AM JST, weekdays):
#   0 10 * * 1-5 ~/usdjpy-analyst/run_daily.sh >> ~/usdjpy-analyst/logs/cron.log 2>&1
#
# Prerequisites:
#   1. Claude Code CLI installed and authenticated (`claude --version`)
#   2. FRED API key set in config.yaml
#   3. Email password in environment: export USDJPY_EMAIL_PASSWORD="your_password"
#   4. Python 3 available with smtplib (standard library)
# =============================================================================

set -euo pipefail

# --- Configuration ---
PROJECT_DIR="$HOME/usdjpy-analyst"
LOG_DIR="$PROJECT_DIR/logs"
OUTPUT_DIR="$PROJECT_DIR/output/daily"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/run_${TODAY}.log"

# --- Setup ---
mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

echo "========================================" | tee -a "$LOG_FILE"
echo "USD/JPY Daily Run — $TODAY $(date +%H:%M:%S)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# --- Check prerequisites ---
if ! command -v claude &> /dev/null; then
    echo "ERROR: Claude Code CLI not found. Install it first." | tee -a "$LOG_FILE"
    exit 1
fi

if [ -z "${USDJPY_EMAIL_PASSWORD:-}" ]; then
    echo "WARNING: USDJPY_EMAIL_PASSWORD not set. Report will be generated but not emailed." | tee -a "$LOG_FILE"
fi

# --- Run Claude Code ---
echo "Starting Claude Code analysis..." | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

claude -p . \
  --allowedTools "Bash(read_only:false),Read,Write,Edit" \
  --max-turns 50 \
  "Read the CLAUDE.md and all skill files under ./skills/usdjpy/. \
   Then execute the /usdjpy-daily workflow: \
   1. Read config.yaml for API keys and settings \
   2. Run Module 01 (Macro): fetch FRED data, compute spread, generate chart \
   3. Run Module 03 (Technicals): fetch price data, compute indicators (skip if module says not yet implemented — use whatever is available) \
   4. Run Module 05 (Cross-Asset): fetch correlated assets, compute correlations (skip if not yet implemented) \
   5. Run Module 07 (Checklist): aggregate all available signals into the checklist grid \
   6. Save the complete report as ./output/daily/${TODAY}.md \
   7. Save any charts as PNG files in ./output/daily/ \
   If any module is not yet fully implemented, note it as N/A in the checklist and continue." \
  2>&1 | tee -a "$LOG_FILE"

CLAUDE_EXIT=$?

if [ $CLAUDE_EXIT -ne 0 ]; then
    echo "ERROR: Claude Code exited with code $CLAUDE_EXIT" | tee -a "$LOG_FILE"
fi

# --- Find the report ---
REPORT=""

# Try exact date match first
if [ -f "$OUTPUT_DIR/${TODAY}.md" ]; then
    REPORT="$OUTPUT_DIR/${TODAY}.md"
else
    # Fallback: most recent .md file
    REPORT=$(ls -t "$OUTPUT_DIR"/*.md 2>/dev/null | head -1)
fi

if [ -z "$REPORT" ] || [ ! -f "$REPORT" ]; then
    echo "ERROR: No report file found in $OUTPUT_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

echo "Report generated: $REPORT" | tee -a "$LOG_FILE"

# --- Collect chart attachments ---
CHARTS=$(ls "$OUTPUT_DIR"/*"${TODAY}"*.png 2>/dev/null || true)
if [ -n "$CHARTS" ]; then
    echo "Charts found: $CHARTS" | tee -a "$LOG_FILE"
fi

# --- Send email ---
if [ -n "${USDJPY_EMAIL_PASSWORD:-}" ]; then
    echo "Sending email..." | tee -a "$LOG_FILE"
    python3 "$PROJECT_DIR/send_report.py" "$REPORT" $CHARTS 2>&1 | tee -a "$LOG_FILE"
    echo "Email sent successfully." | tee -a "$LOG_FILE"
else
    echo "Skipping email (no password set)." | tee -a "$LOG_FILE"
fi

echo "Done. $(date +%H:%M:%S)" | tee -a "$LOG_FILE"
