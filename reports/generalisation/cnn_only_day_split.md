# Day-based split: train monday, tuesday, wednesday -> evaluate thursday, friday

| | ours (entropy + distance) | ours (entropy only) | RF |
|---|---|---|---|
| attack_caught_or_referred | 91.71% | 77.45% | 98.55% |
| attack_missed | 8.29% | 22.55% | 1.45% |
| benign_auto_closed | 99.53% | 99.79% | 99.50% |
| benign_false_alert | 0.00% | 0.00% | 0.00% |
| benign_referred | 0.47% | 0.21% | 0.50% |
| overall_referral | 14.93% | 11.51% | 17.03% |

## Per class (share missed = auto-closed as benign)

| class | n | seen in training? | ours: review | ours: missed | RF: review | RF: missed |
|---|---|---|---|---|---|---|
| BENIGN | 448,118 | yes | 0.5% | 99.5% | 0.5% | 99.5% |
| DDoS | 80,873 | **no** | 93.7% | 0.2% | 100.0% | 0.0% |
| Portscan | 6,540 | **no** | 10.1% | 89.5% | 93.2% | 6.8% |
| Web Attack | 1,748 | **no** | 92.3% | 7.7% | 93.9% | 6.1% |
| Botnet | 1,631 | **no** | 16.0% | 84.0% | 53.8% | 46.2% |
| Infiltration | 56 | **no** | 50.0% | 50.0% | 91.1% | 8.9% |