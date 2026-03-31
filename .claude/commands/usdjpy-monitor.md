Run Module 09 (Scenario Monitor) — live check against the most recent SMC report.

Steps:
1. Read `./skills/usdjpy/modules/09_scenario_monitor.md` for full spec
2. Run the live check:
   ```
   python3 scripts/run_scenario_monitor.py --mode check
   ```
3. Review the output and print key findings:
   - Which scenario is ACTIVE / APPROACHING / NOT TRIGGERED
   - Entry zone hit status
   - Current P&L if entry was hit
   - Distance to target and stop
4. The script saves to `./output/daily/monitor_YYYY-MM-DD.md`

If no SMC report exists, tell the user to run /usdjpy-entry first.
