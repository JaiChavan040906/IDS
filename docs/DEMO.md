# Demo guide (about 10 minutes)

A walkthrough of the full human-in-the-loop cycle for the project presentation.

## Before the demo

1. Build the frontend once: `cd frontend && npm run build`
2. Start from a clean database so the numbers are fresh: stop the server, delete `data/ids.db*`.
3. Start the portal: `.venv/Scripts/python -m uvicorn ids.api.main:app --port 8000`
4. Open <http://localhost:8000>. Have two browser windows ready: one logged in as `analyst`,
   one (private window) as `admin`.
5. Optional speed-up: in Admin → Overview set *Flows per tick* to 200 and *Seconds per tick* to 1,
   then press **Start replay** a few minutes before presenting so the queues have content.

## Script

### 1. The problem (ABOUT page, 1 min)
- "Classic IDS models are either confidently right or confidently wrong. Ours knows when it is unsure."
- Point at the flow diagram: detect → uncertainty → analyst → Knowledge Repository → controlled retraining.
- Point at the headline numbers: they come from the active model's validation results.

### 2. Live traffic (Admin → Overview, 1 min)
- Start the replay (mode **Attack mix** for a lively demo; **Sequential** is the realistic ~83% benign stream).
- Explain: this is the held-out **test split** replayed flow by flow. The true label travels with the
  flow only for evaluation. The model never sees it, and neither does the analyst.

### 3. Analyst dashboard (Analyst → Dashboard, 1 min)
- Flows scored, auto-closed benign, confident alerts, sent to review. Stress the small review share:
  analysts only see the uncertain part.

### 4. Review an uncertain alert (Analyst → Review queue → open one, 3 min)
- **Flow context**: IPs, ports, time. Context for the human, never model input.
- **Model verdict**: top classes with probabilities, the Random Forest second opinion, and the
  two uncertainty meters with their thresholds (white marks). Read out the "why flagged" reason.
- **What stands out**: the most unusual features (z-scores), a simple, honest evidence view.
- **Similar past incidents**: retrieved from the Knowledge Repository by embedding similarity.
- Fill the form: verdict, attack type, reason, context, evidence, confidence, tags → **Save**.
- Show it appearing in **Knowledge Repository** and, when opening another similar alert,
  in its *Similar past incidents*.

### 5. Admin verification and retraining (Admin, 3 min)
- **Verify feedback**: only verified decisions can train the model; "unsure" and new attack types never do.
- **Retraining**: point at the acceptance criteria, fixed *before* training. Start a run
  (needs ≥ 20 verified items; the log streams live).
- Open the finished job: pass/fail per check, base vs candidate on the fixed benchmark and on held-out feedback.
- **Models**: approve → deploy (the replay switches models without a restart). Then show **Roll back**.
- **Audit log**: every step above is recorded with who/when/what.

### 6. Evidence it works (Admin → Evaluation + reports, 1 min)
- Evaluation tab: live accuracy per model version, analyst accuracy vs. hidden truth.
- Reports: `reports/final/FINAL_REPORT.md` (test set, paper comparison),
  `reports/generalisation/loao.md` (unseen attacks routed to humans), `reports/uncertainty/coverage_risk.png`.

## Honest talking points (likely questions)

- **"Your trees beat the CNN-LSTM?"** Yes, on raw accuracy with a random split, as is common on
  CIC-IDS2017. Our claim is about what happens *around* the model: referral of uncertain and
  unseen attacks to humans, and safe retraining. See `docs/PROJECT_REPORT.md`.
- **"Why a Random Forest inside a CNN-LSTM system?"** Leave-one-attack-out showed the CNN-LSTM is
  confidently wrong on attacks it never saw; the RF second opinion (unsure or disagreeing ->
  review) cut missed unseen Portscan from ~40-80% to 4%. On the test set the hybrid catches
  98.9% of all model errors in the review queue.
- **"What does it still miss?"** SSH brute force: each login looks normal on its own; it needs
  features spanning many flows (future work).
- **"Why remove destination port?"** Shortcut risk: port 21 means FTP-Patator in this dataset,
  which would not generalise. It also exposed that most Portscan rows were near-duplicates.
- **"Is the GAN augmentation useful?"** Reported honestly in the ablation; the synthetic flows are
  easily told apart from real ones (AUC 1.0) because real features are discrete.
- **"Is the login real?"** Simulated for the project (PBKDF2-hashed passwords, bearer tokens); a
  deployment would add HTTPS, token expiry and a real identity provider.
