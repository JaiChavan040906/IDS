# External data: Friday-02-03-2018_TrafficForML_CICFlowMeter.csv

Model bundle v1. 499,854 flows (random sample of 1,048,575). Measurements matched: 77/82 (filled with typical values: Fwd RST Flags, Bwd RST Flags, ICMP Code, ICMP Type, Total TCP Flow Time).

## Routing

- Auto-closed as normal: 1.31%
- Confident alerts: 0.00%
- Sent to a human: 98.69%

## Against the labels in the file

| | Deployed system (with review) | CNN-LSTM alone |
|---|---|---|
| Attacks caught (alerted or reviewed) | 100.00% | 0.16% |
| Attacks missed (closed as normal) | 0.00% | – |
| False alarms on normal traffic | 0.000% | 10.734% |
| Normal traffic sent to review | 98.20% | – |
| Exact-class accuracy (known classes) | 64.90% | |

## Per label

| label | flows | known class? | review | alert | closed as normal | model's top guesses |
|---|---|---|---|---|---|---|
| BENIGN | 363,433 | yes | 98.2% | 0.0% | 1.8% | BENIGN 89%, Portscan 10%, DoS Slowhttptest 0% |
| Botnet | 136,421 | yes | 100.0% | 0.0% | 0.0% | BENIGN 100%, Portscan 0%, Botnet 0% |