# Baselines - validation set (mean ± std over seeds, %)

Seeds per model: random_forest=3, lightgbm=3

| metric | random_forest | lightgbm |
|---|---|---|
| accuracy | 99.97 ± 0.00 | 99.96 ± 0.00 |
| macro_f1 | 98.54 ± 0.01 | 98.80 ± 0.01 |
| macro_f1_reliable | 99.28 ± 0.02 | 99.06 ± 0.01 |
| bin_precision | 99.93 ± 0.00 | 99.87 ± 0.01 |
| detection_rate | 99.91 ± 0.00 | 99.91 ± 0.01 |
| bin_f1 | 99.92 ± 0.00 | 99.89 ± 0.00 |
| fpr | 0.015 ± 0.001 | 0.026 ± 0.002 |
| fnr | 0.088 ± 0.005 | 0.085 ± 0.005 |

## Per-class recall (%)

| class | random_forest | lightgbm |
|---|---|---|
| BENIGN | 99.99 ± 0.00 | 99.97 ± 0.00 |
| DoS Hulk | 99.99 ± 0.00 | 99.99 ± 0.00 |
| DDoS | 100.00 ± 0.00 | 100.00 ± 0.00 |
| Portscan | 99.80 ± 0.05 | 99.83 ± 0.00 |
| DoS GoldenEye | 99.74 ± 0.00 | 99.91 ± 0.00 |
| DoS Slowloris | 99.77 ± 0.20 | 99.88 ± 0.00 |
| DoS Slowhttptest | 98.69 ± 0.00 | 99.17 ± 0.30 |
| FTP-Patator | 100.00 ± 0.00 | 100.00 ± 0.00 |
| SSH-Patator | 99.55 ± 0.00 | 99.55 ± 0.00 |
| Web Attack | 97.95 ± 0.19 | 99.03 ± 0.00 |
| Botnet | 95.14 ± 0.00 | 90.62 ± 0.00 |
| Infiltration | 80.00 ± 0.00 | 90.00 ± 0.00 |
| Heartbleed | 100.00 ± 0.00 | 100.00 ± 0.00 |