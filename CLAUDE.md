# AI-Based Intrusion Detection System (HITL IDS)

Third-year (TE CMPN) team project. Jai guides decisions; Claude implements.

## One-line summary
An adaptive AI-based IDS: the model detects suspicious network flows, uncertain
cases go to a human security analyst, the analyst's decision plus context is
stored in a Knowledge Repository, and verified feedback improves the model
through controlled, admin-approved retraining.

## Reference paper
"Uncertainty-Aware Adaptive Intrusion Detection Using Hybrid CNN-LSTM with
cWGAN-GP Augmentation and Human-in-the-Loop Feedback" (MDPI, Dec 2025).
Reported: 98% binary accuracy, 96.6% detection rate, 92.1% precision, 94.3% F1.
Their classifier (Table 5): input 46 features -> Conv1D(64,k5,ReLU) ->
MaxPool(2) -> Conv1D(128,k3,ReLU) -> LSTM(128) -> Dropout(0.3) -> Dense softmax.
Uncertainty: temperature scaling + entropy. Augmentation: VAE seeds -> cWGAN-GP.

## Dataset decisions (final)
- ONLY dataset: **Improved CIC-IDS2017** (corrected release, Engelen et al. /
  Liu et al.). Kaggle: ernie55ernie/improved-cicids2017-and-csecicids2018
  -> use the CICIDS2017 folder only.
- Optional, end of project: Improved CSE-CIC-IDS2018 for cross-network testing
  (same CICFlowMeter features).
- CIC-IoT2023: NOT used (different feature set). Future scope only.
- Demo traffic = replay of the untouched test split. No separate demo dataset.

## Decisions made after EDA (configs/data.yaml)
- 27 raw labels -> 13 classes: "Attempted" attacks merged into their attack
  class; Infiltration - Portscan merged into Portscan (identical features);
  Web Attack Brute Force / XSS / SQL Injection grouped as "Web Attack".
- Heartbleed (11 flows) and Infiltration (81) kept but always reported with a
  caveat (`unreliable_classes`); macro-F1 is also reported without them.
- Destination Port excluded from features (shortcut). Consequence: most Portscan
  rows became duplicates (230k -> 7.7k). "Attempted Category" dropped (label leak).
- Dedupe on model-visible features BEFORE the split; rows whose features carry
  two labels are dropped. Result: 1,714,812 flows, 64 features after selection.
- CNN-LSTM: random oversampling of classes < 1000 train rows (train only);
  without it the network ignores Heartbleed/Infiltration.
- Uncertainty routing = temperature-scaled entropy OR Mahalanobis distance on the
  128-d embedding OR a Random Forest second opinion (RF among its most uncertain
  0.5%, or RF disagrees with the CNN-LSTM). The RF was added (Jai's decision) after
  leave-one-attack-out showed the CNN-LSTM is confidently wrong on unseen attacks.
- Deployed model = bundle v1: CNN-LSTM seed 42 + RF seed 42 second opinion.
  Augmentation not used in the deployed model (gain < seed noise).
- The test set HAS BEEN USED (2026-09-26, reports/final/TEST_SET_USED.json).
  Do not tune anything on it; any new model choice needs fresh justification.

## Data rules (do not break)
- Drop identifier/shortcut columns: Flow ID, Src IP, Dst IP, Src Port,
  Timestamp (keep Timestamp aside only for day-based / temporal experiments).
  Treat Destination Port with suspicion.
- Clean column names (strip spaces), remove duplicate columns, handle
  Infinity/NaN, remove duplicate rows.
- Split first (stratified 70/15/15), then fit scaler, feature selector and any
  augmentation on TRAIN only.
- Tiny classes (Heartbleed, Infiltration, SQL Injection) are unreliable:
  group or report separately with caveats.
- Test set is touched once, at the end. Tune on validation only.
- In the demo, the hidden label is never used for prediction or to fill the
  analyst's decision. Keep it only for evaluation.

## Evaluation plan
1. Held-out test set: accuracy, precision, recall, F1, macro-F1, FPR, FNR,
   per-class recall, confusion matrix.
2. Baselines on identical data: Random Forest, XGBoost/LightGBM, CNN-LSTM.
3. Compare to paper's reported numbers.
4. 3-5 random seeds, report mean +/- std.
5. Leave-one-attack-out: unseen attack should be routed to human review.
6. Day-based split test (generalisation; not the main multiclass benchmark).
7. Calibration + coverage-risk curve (referral rate vs error on auto-handled).
8. Ablations: augmentation off, calibration off, LSTM off.
9. Optional: test on CSE-CIC-IDS2018.
Claim (final, supported by results - see docs/PROJECT_REPORT.md section 7):
not "optimal" and not more accurate than tree baselines (RF is slightly better
on this split). All models exceed the paper's reported numbers on the test set;
results are stable across 3 seeds; the LSTM helps (ablation); the deployed
hybrid refers ~1.5% of flows, catches ~99% of model errors in review, is
99.999% accurate on auto-handled flows, and routes most unseen attacks to a
human (5 of 6 held-out types missed <= 10%; SSH brute force is not caught).
Dropped from the claim: "better calibrated" (T = 1.01, already calibrated).

## Build order (status)
1. Dataset inspection / EDA - DONE (reports/eda/)
2. Preprocessing pipeline (saved, reusable) - DONE
3. Baseline models + evaluation - DONE (RF, LightGBM, 3 seeds)
4. CNN-LSTM, compare - DONE (main + augmentation + no-LSTM, 3 seeds)
5. Calibration + uncertainty routing - DONE (hybrid, bundle v1)
6. FastAPI backend (predict endpoint, alerts DB) - DONE
7. Traffic replay service - DONE
8. Analyst dashboard + contextual feedback (decision, reason, context,
   evidence, confidence, comments) - DONE
9. Knowledge Repository + similar-incident retrieval - DONE
10. Admin dashboard (users, models, retraining, approve/reject/deploy/rollback) - DONE
11. Controlled retraining: verified feedback -> candidate model -> evaluate
    on fixed benchmark + feedback set -> admin approval. Acceptance criteria
    decided BEFORE retraining (configs/app.yaml) - DONE
12. Integration, scenario testing, demo prep - DONE (11 tests, docs/DEMO.md,
    docs/PROJECT_REPORT.md, leave-one-attack-out, day split, final test).
Open / future: CSE-CIC-IDS2018 cross-dataset test (plan step 9), multi-flow
features for SSH brute force / Botnet, retraining the RF second opinion too.

## Where things are
- configs/*.yaml: every setting. scripts/: pipeline steps (see README table).
- src/ids/: data, preprocessing, metrics, nn, augment, uncertainty, bundle.
- src/ids/api/: FastAPI app (db, security, routers/, services/).
- frontend/: React + Vite. artifacts/bundles/<version>/: deployable model bundle.
- Run portal: `.venv/Scripts/python -m uvicorn ids.api.main:app --port 8000`
  (build frontend first). Tests: `.venv/Scripts/python -m pytest`.
- Machine: 7.7 GB RAM - run one heavy job at a time (parallel jobs swap).

## Users
- Security Analyst: reviews alerts, gives contextual feedback, searches KR.
- Administrator: users/roles, model versions, retraining, deploy/rollback,
  system health, audit logs.

## Frontend
Pages: ABOUT | ANALYST | ADMINISTRATION. Login for Analyst and Admin
(simulated first). Visual style inspired by (not copied from) Secuby Framer site.

## Working style
- Explain choices simply; Jai is learning as we build.
- Save model + preprocessing + feature order + label map + calibration +
  thresholds together so the portal uses identical transforms.
- Keep experiments reproducible (seeds, dataset version, configs logged).
