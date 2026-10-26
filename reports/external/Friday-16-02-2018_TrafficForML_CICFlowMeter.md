# External data: Friday-16-02-2018_TrafficForML_CICFlowMeter.csv

Model bundle v1. 499,854 flows (random sample of 1,048,575). Measurements matched: 77/82 (filled with typical values: Fwd RST Flags, Bwd RST Flags, ICMP Code, ICMP Type, Total TCP Flow Time).

## Routing

- Auto-closed as normal: 0.00%
- Confident alerts: 0.00%
- Sent to a human: 100.00%

## Against the labels in the file

| | Deployed system (with review) | CNN-LSTM alone |
|---|---|---|
| Attacks caught (alerted or reviewed) | 100.00% | 95.56% |
| Attacks missed (closed as normal) | 0.00% | – |
| False alarms on normal traffic | 0.000% | 0.413% |
| Normal traffic sent to review | 100.00% | – |
| Exact-class accuracy (known classes) | 42.36% | |

## Per label

| label | flows | known class? | review | alert | closed as normal | model's top guesses |
|---|---|---|---|---|---|---|
| DoS Hulk | 220,894 | yes | 100.0% | 0.0% | 0.0% | Portscan 94%, BENIGN 6% |
| BENIGN | 212,601 | yes | 100.0% | 0.0% | 0.0% | BENIGN 100%, Portscan 0% |
| DoS Slowhttptest | 66,359 | yes | 100.0% | 0.0% | 0.0% | Portscan 100% |