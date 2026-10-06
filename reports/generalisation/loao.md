# Leave-one-attack-out (unseen attack handling)

Each row: the model was trained WITHOUT that attack. Shares of the unseen attack's flows.
Success = sent to review or raised as some attack. Failure = auto-closed as benign.

Missed = share of the unseen attack's flows auto-closed as benign (lower is better).

| held-out attack | n | **hybrid (deployed)** | CNN-LSTM (entropy + distance) | CNN-LSTM (entropy only) | RF alone | hybrid: review / auto-alert | normal-traffic referral hybrid / CNN-LSTM / RF |
|---|---|---|---|---|---|---|---|
| DDoS | 80,873 | **0.0%** | 0.0% | 0.0% | 0.0% | 100.0% / 0.0% | 1.44% / 1.27% / 0.63% |
| Portscan | 6,540 | **4.3%** | 39.7% | 46.3% | 5.3% | 95.7% / 0.0% | 1.56% / 1.36% / 0.51% |
| Botnet | 1,631 | **10.2%** | 12.4% | 12.4% | 10.8% | 89.8% / 0.0% | 1.36% / 1.19% / 0.52% |
| Web Attack | 1,748 | **5.0%** | 97.0% | 97.0% | 6.4% | 95.0% / 0.0% | 1.33% / 1.19% / 0.54% |
| SSH-Patator | 2,540 | **98.9%** | 99.4% | 99.4% | 98.2% | 1.1% / 0.0% | 1.35% / 1.22% / 0.55% |
| DoS Slowloris | 4,847 | **2.4%** | 3.2% | 3.2% | 2.4% | 97.6% / 0.0% | 1.35% / 1.20% / 0.56% |