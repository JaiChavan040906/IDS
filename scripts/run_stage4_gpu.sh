#!/usr/bin/env bash
# Stage 4 GPU chain: augmenter -> CNN-LSTM x3 -> CNN-LSTM+aug x3 -> CNN-only x3
set -e
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
PY=.venv/Scripts/python
mkdir -p reports/cnn_lstm reports/augment
$PY -u scripts/train_augmenter.py                                   > reports/augment/train_log.txt 2>&1
$PY -u scripts/train_cnn_lstm.py                                    > reports/cnn_lstm/train_log.txt 2>&1
$PY -u scripts/train_cnn_lstm.py --name cnn_lstm_aug --augment artifacts/augment/synthetic.npz > reports/cnn_lstm/train_log_aug.txt 2>&1
$PY -u scripts/train_cnn_lstm.py --name cnn_only --no-lstm          > reports/cnn_lstm/train_log_cnn_only.txt 2>&1
echo STAGE4_DONE
