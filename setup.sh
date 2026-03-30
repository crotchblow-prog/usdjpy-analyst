#!/bin/bash
# =============================================================================
# USD/JPY Analyst — First-Time Setup
# =============================================================================
# Run this once after extracting the project to configure everything.
#
# Usage: bash setup.sh
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Setting up USD/JPY Analyst in: $PROJECT_DIR"
echo ""

# --- 1. Create directories ---
echo "1. Creating directories..."
mkdir -p "$PROJECT_DIR"/{data/raw,data/processed,output/daily,output/weekly,output/journal,logs}
echo "   Done."

# --- 2. Make scripts executable ---
echo "2. Setting permissions..."
chmod +x "$PROJECT_DIR/run_daily.sh"
chmod +x "$PROJECT_DIR/run_weekly.sh"
echo "   Done."

# --- 3. Check Python ---
echo "3. Checking Python..."
if command -v python3 &> /dev/null; then
    echo "   Python3 found: $(python3 --version)"
else
    echo "   WARNING: Python3 not found. Email sending won't work."
fi

# --- 4. Install PyYAML if needed ---
echo "4. Checking PyYAML..."
if python3 -c "import yaml" 2>/dev/null; then
    echo "   PyYAML already installed."
else
    echo "   Installing PyYAML..."
    pip3 install pyyaml
fi

# --- 5. Check Claude Code CLI ---
echo "5. Checking Claude Code CLI..."
if command -v claude &> /dev/null; then
    echo "   Claude CLI found: $(claude --version 2>&1 | head -1)"
else
    echo "   WARNING: Claude Code CLI not found."
    echo "   Install it: npm install -g @anthropic-ai/claude-code"
fi

# --- 6. Prompt for configuration ---
echo ""
echo "=== Configuration ==="
echo ""

# FRED API key
read -p "Enter your FRED API key (or press Enter to keep DEMO_KEY): " FRED_KEY
if [ -n "$FRED_KEY" ]; then
    sed -i.bak "s/api_key: \"DEMO_KEY\"/api_key: \"$FRED_KEY\"/" "$PROJECT_DIR/config.yaml"
    echo "   FRED API key updated."
else
    echo "   Keeping DEMO_KEY (rate-limited). Get a free key at:"
    echo "   https://fred.stlouisfed.org/docs/api/api_key.html"
fi

# Email recipient
read -p "Enter your email address for daily reports: " EMAIL
if [ -n "$EMAIL" ]; then
    sed -i.bak "s/to_address: \"YOUR_PERSONAL_EMAIL\"/to_address: \"$EMAIL\"/" "$PROJECT_DIR/config.yaml"
    echo "   Email recipient updated."
fi

# Email password
echo ""
echo "   To enable email delivery, set your SMTP password:"
echo "   export USDJPY_EMAIL_PASSWORD=\"your_namecheap_email_password\""
echo ""
echo "   Add this line to your ~/.bashrc or ~/.zshrc to persist it."

# --- 7. Set up cron ---
echo ""
echo "=== Cron Setup ==="
echo ""
echo "   Add these lines to your crontab (run: crontab -e):"
echo ""
echo "   # USD/JPY Daily Report — 10:00 AM JST, Mon-Fri"
echo "   0 10 * * 1-5 $PROJECT_DIR/run_daily.sh >> $PROJECT_DIR/logs/cron.log 2>&1"
echo ""
echo "   # USD/JPY Weekly Report — 10:00 AM JST, Fridays"
echo "   0 10 * * 5 $PROJECT_DIR/run_weekly.sh >> $PROJECT_DIR/logs/cron.log 2>&1"
echo ""
echo "   NOTE: If your system timezone is NOT JST, adjust the cron hour."
echo "   JST = UTC+9, so 10:00 AM JST = 01:00 UTC"
echo "   For UTC cron: 0 1 * * 1-5 ..."
echo ""

# --- 8. Clean up ---
rm -f "$PROJECT_DIR/config.yaml.bak"

echo "=== Setup Complete ==="
echo ""
echo "Test it now:"
echo "  cd $PROJECT_DIR"
echo "  claude -p . \"Execute /usdjpy-daily\""
echo ""
