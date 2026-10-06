# Sentinel: Human-in-the-Loop AI Intrusion Detection System

TE Computer Engineering project. An adaptive IDS: a CNN-LSTM classifies network
flows, uncertain flows go to a human security analyst, the analyst's decision and
context are stored in a Knowledge Repository, and verified feedback improves the
model through controlled, admin-approved retraining.

Results and design decisions: [`docs/PROJECT_REPORT.md`](docs/PROJECT_REPORT.md).
Demo walkthrough: [`docs/DEMO.md`](docs/DEMO.md).

## Architecture

```
data/raw (Improved CIC-IDS2017, 5 day CSVs)
   │  scripts/prepare_data.py      clean, map labels, dedupe, split 70/15/15, fit transform on TRAIN
   ▼
data/processed/{train,val,test}.parquet  +  artifacts/preprocessing/
   │  scripts/train_baselines.py   Random Forest, LightGBM            (validation only)
   │  scripts/train_augmenter.py   cWGAN-GP minority augmentation      (train only)
   │  scripts/train_cnn_lstm.py    CNN-LSTM (paper Table 5) + ablations (validation only)
   │  scripts/calibrate.py         temperature scaling; routing = entropy + Mahalanobis distance
   │                               + Random Forest second opinion (hybrid)
   ▼
artifacts/bundles/v1/   CNN-LSTM + RF second opinion + preprocessing + label map + calibration + thresholds
   │
   ▼
FastAPI (src/ids/api)  ── SQLite data/ids.db
   ├─ replay service       streams the untouched test split through the active model
   ├─ analyst API          alert queue, alert detail, contextual feedback, KR search
   ├─ Knowledge Repository similar-incident retrieval (cosine on model embeddings)
   ├─ admin API            users, feedback verification, models, audit, health, replay
   └─ retraining service   verified feedback -> candidate -> fixed criteria -> admin approval
   ▲
React frontend (frontend/)  ABOUT | ANALYST | ADMINISTRATION
```

## Setup

Requirements: Python 3.11+ (tested on 3.13), Node 20+, optionally an NVIDIA GPU.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
.venv/Scripts/python -m pip install -e .
```

(On Linux/macOS use `.venv/bin/python`. For CPU-only PyTorch drop the `--index-url`.)

Dataset: download <https://www.kaggle.com/datasets/ernie55ernie/improved-cicids2017-and-csecicids2018>
and copy the five **CICIDS2017** CSVs (`monday.csv` … `friday.csv`) into `data/raw/`.

## Reproduce the ML pipeline

Each step writes its outputs and a report under `reports/`. Run from the project root.

| Step | Command | Time* |
|---|---|---|
| 1. EDA | `.venv/Scripts/python scripts/inspect_dataset.py` | 3 min |
| 2. Preprocess | `.venv/Scripts/python scripts/prepare_data.py` | 2 min |
| 3. Baselines | `.venv/Scripts/python scripts/train_baselines.py` | 15 min |
| 4. Augmenter + CNN-LSTM + ablations | `bash scripts/run_stage4_gpu.sh` | ~3 h |
| 5. Calibrate + bundle | `.venv/Scripts/python scripts/calibrate.py --model-dir artifacts/models/cnn_lstm/seed_42 --version v1` | 3 min |
| Unseen attacks | `.venv/Scripts/python scripts/generalisation.py loao` | ~2 h |
| Unseen days | `.venv/Scripts/python scripts/generalisation.py days` | 20 min |
| Final test (once!) | `.venv/Scripts/python scripts/final_test.py` | 5 min |
| Replay data | `.venv/Scripts/python scripts/build_replay_set.py` | 1 min |

\*i5-1240P, 7.7 GB RAM, RTX 2050. Run heavy steps one at a time on this machine; parallel
GPU jobs ran out of memory and swapped. Headline results: [`docs/PROJECT_REPORT.md`](docs/PROJECT_REPORT.md).

Every setting lives in `configs/*.yaml`; seeds are fixed; each report records the config and
the sha256 of every raw file (`artifacts/preprocessing/prep_report.json`).

## Run the portal

```bash
cd frontend && npm install && npm run build && cd ..
.venv/Scripts/python -m uvicorn ids.api.main:app --port 8000
```

Open <http://localhost:8000>. Demo logins (simulated, see `configs/app.yaml`):

| user | password | role |
|---|---|---|
| analyst | analyst123 | Security Analyst |
| analyst2 | analyst123 | Security Analyst |
| admin | admin123 | Administrator |

For frontend development with hot reload: run uvicorn as above, then `cd frontend && npm run dev`
(Vite proxies `/api` to port 8000).

To start from a clean database, stop the server and delete `data/ids.db*`.

## Tests

```bash
.venv/Scripts/python -m pytest
```

Covers preprocessing, metrics, calibration/routing, and an end-to-end API scenario
(replay → alerts → feedback → KR → verification → retraining → approve → deploy →
rollback → audit), including a check that hidden labels never reach analyst endpoints.

## Rules this project keeps

- Identifier columns (Flow ID, IPs, source port, timestamp) and destination port are never model inputs.
- Split first; scaler, feature selection, augmentation and oversampling are fitted on train only.
- Tune on validation. The test split is used once (`reports/final/TEST_SET_USED.json`).
- In the demo, the hidden label is never used for prediction or to fill the analyst's decision.
- Retraining acceptance criteria are fixed in `configs/app.yaml` and copied into each job before training.
- No model is deployed without passing its criteria and an administrator's approval.

## Layout

```
configs/        all settings (data, models, uncertainty, generalisation, app)
scripts/        runnable pipeline steps
src/ids/        library: data, preprocessing, metrics, nn, augment, uncertainty, bundle
src/ids/api/    FastAPI app: db, security, routers/, services/
frontend/       React + Vite portal
tests/          pytest suite
reports/        generated results (EDA, baselines, CNN-LSTM, uncertainty, generalisation, final)
docs/           project report and demo guide
```
