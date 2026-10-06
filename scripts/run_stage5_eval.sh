#!/usr/bin/env bash
# After Stage 4: calibrate + bundle v1, then generalisation experiments.
set -e
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
PY=.venv/Scripts/python
mkdir -p reports/uncertainty reports/generalisation
[ -f artifacts/bundles/v1/manifest.json ] || $PY -u scripts/calibrate.py --model-dir artifacts/models/cnn_lstm/seed_42 --version v1 > reports/uncertainty/calibrate_log.txt 2>&1
$PY -u scripts/generalisation.py loao > reports/generalisation/loao_log.txt 2>&1
$PY -u scripts/generalisation.py days > reports/generalisation/days_log.txt 2>&1
echo STAGE5_DONE
