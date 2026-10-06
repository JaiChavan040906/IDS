# Leave-one-attack-out (unseen attack handling)

Each row: the model was trained WITHOUT that attack. Shares of the unseen attack's flows.
Success = sent to review or raised as some attack. Failure = auto-closed as benign.

| held-out attack | n | ours: review | ours: auto-alert | **ours: missed** | entropy-only: missed | RF: review | RF: auto-alert | **RF: missed** | in-dist. referral ours / RF |
|---|---|---|---|---|---|---|---|---|---|
| DDoS | 80,873 | 87.9% | 0.0% | **12.1%** | 12.2% | 100.0% | 0.0% | **0.0%** | 1.24% / 0.63% |
| Portscan | 6,540 | 19.1% | 0.4% | **80.5%** | 87.2% | 94.7% | 0.0% | **5.3%** | 1.32% / 0.51% |
| Botnet | 1,631 | 67.1% | 0.0% | **32.9%** | 32.9% | 89.2% | 0.0% | **10.8%** | 1.22% / 0.52% |
| Web Attack | 1,748 | 86.9% | 0.0% | **13.1%** | 13.1% | 93.6% | 0.0% | **6.4%** | 1.30% / 0.54% |
| SSH-Patator | 2,540 | 0.4% | 0.0% | **99.6%** | 99.6% | 1.8% | 0.0% | **98.2%** | 1.16% / 0.55% |
| DoS Slowloris | 4,847 | 88.6% | 0.0% | **11.4%** | 11.5% | 87.2% | 10.3% | **2.4%** | 1.25% / 0.56% |