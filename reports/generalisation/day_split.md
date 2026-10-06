# Day-based split: train monday, tuesday, wednesday -> evaluate thursday, friday

| | **hybrid (deployed)** | CNN-LSTM (entropy + distance) | CNN-LSTM (entropy only) | RF alone |
|---|---|---|---|---|
| attack_caught_or_referred | **98.62%** | 83.54% | 64.72% | 98.55% |
| attack_missed | **1.38%** | 16.46% | 35.28% | 1.45% |
| benign_auto_closed | **99.24%** | 99.52% | 99.78% | 99.50% |
| benign_false_alert | **0.00%** | 0.00% | 0.00% | 0.00% |
| benign_referred | **0.76%** | 0.48% | 0.22% | 0.50% |
| overall_referral | **17.26%** | 14.01% | 10.27% | 17.03% |

## Per class (share missed = auto-closed as benign)

| class | n | seen in training? | hybrid: missed | CNN-LSTM: missed | RF: missed |
|---|---|---|---|---|---|
| BENIGN | 448,118 | yes | **99.2%** | 99.5% | 99.5% |
| DDoS | 80,873 | **no** | **0.0%** | 7.2% | 0.0% |
| Portscan | 6,540 | **no** | **7.7%** | 89.8% | 6.8% |
| Web Attack | 1,748 | **no** | **7.6%** | 99.8% | 6.1% |
| Botnet | 1,631 | **no** | **37.7%** | 91.4% | 46.2% |
| Infiltration | 56 | **no** | **5.4%** | 41.1% | 8.9% |