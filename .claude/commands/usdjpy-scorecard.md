Run Module 09 (Scenario Scorecard) — score the playbook after the 12h window closes.

Steps:
1. Read `./skills/usdjpy/modules/09_scenario_monitor.md` for full spec
2. Run the scorecard:
   ```
   python3 scripts/run_scenario_monitor.py --mode scorecard
   ```
3. Review the output and print key findings:
   - Which scenario best matched actual price action
   - Outcome scores (HIT / PARTIAL / MISS) for each scenario
   - Theoretical P&L, MAE, MFE
   - Running stats (if 10+ reports logged)
4. The script saves:
   - Report: `./output/scorecard/scorecard_YYYY-MM-DD.md`
   - CSV row: `./output/scorecard/scenario_log.csv`

If the 12h window hasn't closed yet, the script will report the remaining time.
