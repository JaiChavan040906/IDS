# Project report: Sentinel HITL Intrusion Detection System

TE Computer Engineering team project. All numbers below are reproducible with the
commands in the README; each comes from a file under `reports/`.

## 1. What we built

An adaptive intrusion detection system with a human in the loop:

1. A **CNN-LSTM** (reference paper, Table 5) classifies each network flow into BENIGN or one
   of 12 attack classes.
2. **Uncertainty routing** decides who handles each flow:
   *auto-benign* (closed), *auto-alert* (confident attack) or *review* (sent to an analyst).
3. A **security analyst** reviews uncertain flows with context, evidence and similar past
   incidents, and records a contextual decision (verdict, class, reason, context,
   evidence, confidence, comments, tags).
4. Decisions go into a **Knowledge Repository** with similar-incident retrieval.
5. An **administrator** verifies feedback and launches **controlled retraining**: a candidate
   model is evaluated against acceptance criteria fixed before training, and is only deployed
   after the admin approves it. Rollback and a full audit log are included.

## 2. Data (Stage 1-2)

Improved CIC-IDS2017 (Engelen et al.), five day files, 2,099,976 flows, 91 columns.

| Decision | Why |
|---|---|
| Drop Flow ID, IPs, Src Port, Timestamp, `id` | identifiers / shortcuts |
| Drop `Attempted Category` | it encodes the label (leak) |
| Exclude Destination Port | shortcut (port 21 means FTP-Patator in this data) |
| 27 raw labels -> 13 classes | "Attempted" merged into the attack; Infiltration-Portscan = Portscan (identical features); 3 web attacks grouped |
| De-duplicate on model features **before** splitting | 385,106 duplicates would otherwise leak between train and test |
| Drop 58 rows whose features carry two labels | no model can separate them |
| Stratified 70/15/15 split, seed 42 | transforms fitted on train only |
| 82 -> 64 features | 1 constant, 17 near-copies (|corr| > 0.99) removed, on train |

Result: **1,714,812 flows** (1.20M train / 257k val / 257k test). Excluding destination port
revealed that most Portscan rows were copies (230k -> 7.7k). Heartbleed (11 flows) and
Infiltration (81) are too small to trust and are always reported with a caveat;
"macro-F1 (reliable)" excludes them.

## 3. Models (Stage 3-4), validation set, mean ± std over 3 seeds

| Model | Accuracy | Macro-F1 (reliable) | Detection rate | FPR |
|---|---|---|---|---|
| Random Forest | 99.97% | **99.28 ± 0.02%** | 99.91% | **0.015%** |
| LightGBM | 99.96% | 99.06 ± 0.01% | 99.91% | 0.026% |
| CNN-LSTM | 99.90% | 98.21 ± 0.93% | 99.75% | 0.052% |
| CNN-LSTM + cWGAN-GP augmentation | 99.92% | 98.53 ± 0.30% | 99.84% | 0.047% |
| CNN only (LSTM removed) | 99.79% | 96.13 ± 0.40% | 99.23% | 0.062% |

What we learned:
- **The LSTM matters** (ablation): removing it costs ~2 points of macro-F1; Portscan recall falls 96% -> 88%.
- **Augmentation helps a little and stabilises seeds**, but the gain is smaller than the seed
  variation. The GAN's samples are easy to tell from real ones (real-vs-fake AUC = 1.0), because
  real flow features are discrete counts; the paper's VAE seeding might help here.
- **Tree models are the most accurate** on this random split, as is common for CIC-IDS2017.
- Two fixes were needed: LightGBM diverged after 12 rounds until its leaf values were capped;
  the CNN-LSTM ignored the two tiny classes (macro-F1 capped at ~0.85) until they were
  randomly oversampled in the training set.

## 4. Calibration and uncertainty (Stage 5)

- Temperature scaling found T = 1.01: the CNN-LSTM was **already well calibrated**
  (ECE 0.023% -> 0.022%). The "calibration off" ablation therefore changes almost nothing.
- Routing signals: normalised entropy (most uncertain 1% of validation flows) and
  Mahalanobis distance on the 128-d embedding (99.5th percentile of known traffic).

### The finding that changed the design

Leave-one-attack-out (train without one attack, then see what happens to it) showed that the
CNN-LSTM is **confidently wrong on unseen attacks**, while a Random Forest's vote spread notices
them. Example from the first run: unseen Portscan auto-closed as benign 80.5% of the time by the
CNN-LSTM vs 5.3% by the RF. The distance signal helped (on the day split it cut missed attacks
from 35% to 16%) but not enough.

We therefore deployed a **hybrid**: the CNN-LSTM classifies, and a flow is also sent to review
when a Random Forest "second opinion" is among its most uncertain 0.5% or **disagrees** with the
CNN-LSTM. This was chosen after seeing leave-one-attack-out results, so those results are not an
independent test of it; the untouched test set (section 6) is.

## 5. Generalisation (evaluation steps 5-6)

### Leave-one-attack-out: share of the unseen attack auto-closed as benign (lower is better)

| Held-out attack | Flows | **Hybrid (deployed)** | CNN-LSTM alone | RF alone |
|---|---|---|---|---|
| DDoS | 80,873 | **0.0%** | 0.0% | 0.0% |
| Portscan | 6,540 | **4.3%** | 39.7% | 5.3% |
| Botnet | 1,631 | **10.2%** | 12.4% | 10.8% |
| Web Attack | 1,748 | **5.0%** | 97.0% | 6.4% |
| SSH-Patator | 2,540 | 98.9% | 99.4% | 98.2% |
| DoS Slowloris | 4,847 | **2.4%** | 3.2% | 2.4% |

Normal-traffic referral: hybrid ~1.4%, CNN-LSTM ~1.25%, RF ~0.55%.

- The hybrid misses the fewest unseen attacks in 5 of 6 cases. It costs extra analyst work:
  it refers about 2.5x as much normal traffic as the RF alone.
- **SSH-Patator is not caught by anything**: brute-force logins look like normal SSH sessions
  flow by flow. Detecting it needs context across flows (many logins from one host), which
  a per-flow model cannot see. This is a genuine limitation and future work.
- The CNN-LSTM alone is **unstable** across training runs on unseen attacks (e.g. Web Attack
  13% missed in one run, 97% in another; one seed per attack). The second opinion removes most
  of this risk.

### Day-based split: train Monday-Wednesday, evaluate Thursday-Friday (every attack type on those days is unseen in training)

| | **Hybrid** | CNN-LSTM (entropy + distance) | CNN-LSTM (entropy only) | RF alone |
|---|---|---|---|---|
| Attack flows missed | **1.38%** | 16.46% | 35.28% | 1.45% |
| Benign flows referred | 0.76% | 0.48% | 0.22% | 0.50% |

Per class (missed): Portscan 7.7%, Web Attack 7.6%, Infiltration 5.4%, DDoS 0.0%, but
**Botnet 37.7%** (RF alone 46.2%): Botnet traffic on a new day is still hard.

## 6. Final test set (evaluated once; `reports/final/`)

257,222 flows, never used for training, tuning, calibration or threshold selection.

### Against the paper (binary: attack vs benign; mean over 3 seeds)

| | Paper (reported) | Random Forest | LightGBM | CNN-LSTM | CNN-LSTM + aug | CNN only |
|---|---|---|---|---|---|---|
| Accuracy | 98.0% | 99.97% | 99.96% | 99.89% | 99.92% | 99.80% |
| Detection rate | 96.6% | 99.92% | 99.91% | 99.75% | 99.86% | 99.23% |
| Precision | 92.1% | 99.90% | 99.84% | 99.71% | 99.74% | 99.70% |
| F1 | 94.3% | 99.91% | 99.88% | 99.73% | 99.80% | 99.46% |

(Our accuracy row is 13-class accuracy.) Differences from the paper can come from its preprocessing,
the corrected dataset release, and our de-duplication; they are not a like-for-like comparison.

### The deployed system (bundle v1: CNN-LSTM seed 42 + RF second opinion)

| | **Hybrid (deployed)** | CNN-LSTM-only routing |
|---|---|---|
| Sent to analyst | 1.48% | 1.33% |
| Accuracy on auto-handled flows | **99.999%** | 99.997% |
| Share of model errors caught by review | **98.9%** | 96.0% |
| Attacks auto-closed as benign | **2** (0.005% of attacks) | 7 |
| Benign flows raised as confident alerts | **0** | 0 |

Review is concentrated where the model is weakest: 100% of Web Attack and Infiltration flows,
75% of DoS Slowhttptest, 63% of Botnet, 38% of Portscan; under 1% of BENIGN, DDoS and DoS Hulk.

## 7. The claim we can support

Not "optimal", and not "more accurate than the baselines": on this dataset tree ensembles are
slightly more accurate. What the evidence supports:

1. Every model, including our CNN-LSTM, exceeds the paper's reported numbers on the held-out test set.
2. Results are stable across 3 seeds (the CNN-LSTM less so than trees; augmentation reduces this).
3. The LSTM layer is a real contributor (ablation).
4. The deployed human-in-the-loop system sends ~1.5% of traffic to an analyst, catches ~99% of all
   model errors in that queue, and is 99.999% accurate on what it handles alone.
5. On attacks it has never seen, the hybrid routes most flows to a human (5 of 6 attack types
   missed ≤ 10%), where the CNN-LSTM alone often fails silently. SSH brute force is the exception.

## 8. The portal (Stages 6-11)

- **FastAPI + SQLite** backend: alerts, contextual feedback, Knowledge Repository, users,
  model registry, retraining jobs, traffic stats, audit log. Simulated login (PBKDF2 + tokens).
- **Replay service** streams the untouched test split; the true label is kept only for the admin's
  evaluation panel and is never sent to analysts (checked by an automated test).
- **Similar-incident retrieval**: cosine similarity of CNN-LSTM embeddings, recomputed per model version.
- **Controlled retraining**: verified feedback + 200k original rows -> fine-tune -> recalibrate ->
  evaluate base vs candidate on the fixed benchmark (validation half) and held-out feedback ->
  pass/fail on criteria copied into the job at creation -> admin approve -> deploy (hot swap) / rollback.
- **Frontend**: React (ABOUT | ANALYST | ADMINISTRATION), works down to phone width.
- **Tests**: 11 pytest tests including an end-to-end HITL scenario.
- Live replay: ~0.55 ms per flow on CPU, including the RF second opinion.

## 9. Limitations and future work

- Per-flow models miss multi-flow attacks (SSH brute force, some Botnet); add host/time-window features.
- The RF second opinion is not retrained with analyst feedback (only the CNN-LSTM is).
- Leave-one-attack-out used one seed per attack; the CNN-LSTM's variance there is high.
- GAN augmentation produced unrealistic samples; try the paper's VAE seeding or discrete-aware generation.
- Cross-dataset test on CSE-CIC-IDS2018 (plan step 9) not done yet.
- Login is simulated; a deployment needs HTTPS, token expiry and a real identity provider.

## 10. Where each number comes from

| Section | File |
|---|---|
| EDA | `reports/eda/EDA_SUMMARY.md` |
| Preprocessing | `artifacts/preprocessing/prep_report.json` |
| Baselines, CNN-LSTM, ablations (validation) | `reports/cnn_lstm/val_summary.md`, `reports/baselines/` |
| Augmentation quality | `reports/augment/augment_report.md` |
| Calibration, coverage-risk | `reports/uncertainty/` |
| Leave-one-attack-out, day split | `reports/generalisation/` (`cnn_only_*` = before the hybrid) |
| Final test | `reports/final/FINAL_REPORT.md`, `test_summary.md`, `routing_test.json` |
