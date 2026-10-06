# Final test-set results

Evaluated 2026-09-26 03:29. Test split: 257,222 flows, never used for training, tuning, calibration or threshold selection.

## Paper comparison (binary: attack vs benign)

| | paper (reported) | random_forest | lightgbm | cnn_lstm | cnn_lstm_aug | cnn_only |
|---|---|---|---|---|---|---|
| accuracy | 98.0% | 99.97% | 99.96% | 99.89% | 99.92% | 99.80% |
| detection_rate | 96.6% | 99.92% | 99.91% | 99.75% | 99.86% | 99.23% |
| precision | 92.1% | 99.90% | 99.84% | 99.71% | 99.74% | 99.70% |
| f1 | 94.3% | 99.91% | 99.88% | 99.73% | 99.80% | 99.46% |

Our accuracy is 13-class accuracy; the paper's is binary accuracy.

## Deployed system (calibrated CNN-LSTM + RF second opinion, hybrid routing)

- Sent to analyst: **1.48%** of flows
- Accuracy on the flows handled automatically: **99.999%** (vs 99.932% if nothing were referred)
- Share of all model errors that land in the review queue: **98.9%**
- Attacks auto-closed as benign: 2 (0.005% of attacks)
- Benign flows raised as confident alerts: 0 (0.0000% of benign)

CNN-LSTM-only routing on the same flows (no RF second opinion): referral 1.33%, auto-handled accuracy 99.997%, errors caught 96.0%, attacks missed 7.

Full per-class tables: test_summary.md