# Deploying Sentinel IDS to Hugging Face Spaces

The portal runs as a Docker Space on free CPU hardware and gets a public link like
`https://huggingface.co/spaces/<your-username>/sentinel-ids`.

## What gets uploaded

`scripts/build_space.py` assembles `build/space/` (about 370 MB, 65 files):

| In the Space | Purpose |
|---|---|
| `Dockerfile`, `README.md` (from `deploy/`) | How the Space is built; the Space's description page |
| `src/`, `configs/`, `requirements.txt`, `pyproject.toml` | The application |
| `frontend/dist/` | The built website |
| `artifacts/bundles/v1/`, `artifacts/preprocessing/` | The deployed model and its preprocessing |
| `data/processed/replay.parquet` | Demo traffic (the held-out test flows) |
| `data/processed/train.parquet`, `val.parquet` | Needed for controlled retraining |
| `data/warehouse.db` | Data warehouse (hidden until the admin switches it on) |

No portal database is uploaded: each start creates a fresh one with the users below.

## Passwords

Set these as **Secrets** in the Space (Settings → Variables and secrets → New secret):

| Secret | Used for |
|---|---|
| `IDS_ADMIN_PASSWORD` | the `admin` account |
| `IDS_ANALYST_PASSWORD` | the `analyst` and `analyst2` accounts |

When either is set, the login page no longer shows the demo accounts.

## Steps

1. Build the website and the Space folder (PowerShell, project root):
   ```
   cd frontend; npm run build; cd ..
   .\.venv\Scripts\python.exe scripts\build_space.py
   ```
2. On huggingface.co: **New Space** → name `sentinel-ids` → SDK **Docker** (Blank) → hardware
   **CPU basic (free)** → Public → Create.
3. In the Space: Settings → add the two secrets above.
4. Create an access token: huggingface.co → Settings → Access Tokens → New token (type **Write**).
5. Upload (paste the token when asked):
   ```
   .\.venv\Scripts\python.exe -m pip install -U huggingface_hub
   .\.venv\Scripts\hf.exe auth login
   .\.venv\Scripts\hf.exe upload <your-username>/sentinel-ids build\space . --repo-type=space
   ```
6. The Space builds (about 5-10 minutes the first time), then shows the portal.

## Updating

After code changes: repeat step 1 and the `hf upload` command. The Space rebuilds by itself.

## Notes

- Data (alerts, decisions, retraining jobs) resets whenever the Space restarts or goes to sleep;
  the model and the warehouse are part of the image and always come back.
- Free Spaces sleep after about 48 hours without visitors and wake on the next visit (first load is slow).
- Retraining works but takes a few minutes on the free CPU.
