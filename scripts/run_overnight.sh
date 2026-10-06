#!/usr/bin/env bash
# Hybrid generalisation experiments, then the one-time final test.
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
PY=.venv/Scripts/python
$PY -u scripts/generalisation.py loao > reports/generalisation/loao_log.txt 2>&1 || echo LOAO_FAILED
$PY -u scripts/generalisation.py days > reports/generalisation/days_log.txt 2>&1 || echo DAYS_FAILED
$PY -u scripts/final_test.py > reports/final_test_log.txt 2>&1 || echo FINAL_FAILED
echo OVERNIGHT_DONE
