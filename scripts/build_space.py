"""Assemble the Hugging Face Space folder (build/space) with exactly what the portal needs.

Run from the project root after building the frontend:
    cd frontend && npm run build && cd ..
    .venv/Scripts/python scripts/build_space.py
Then upload build/space to your Space (see docs/DEPLOY.md).
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "space"

# (source, destination inside the Space)
ITEMS = [
    ("deploy/Dockerfile", "Dockerfile"),
    ("deploy/space_README.md", "README.md"),
    ("requirements.txt", "requirements.txt"),
    ("pyproject.toml", "pyproject.toml"),
    ("src", "src"),
    ("configs", "configs"),
    ("frontend/dist", "frontend/dist"),                       # the built website
    ("artifacts/bundles/v1", "artifacts/bundles/v1"),         # the deployed model
    ("artifacts/preprocessing", "artifacts/preprocessing"),   # scaler + label map (retraining)
    ("data/processed/replay.parquet", "data/processed/replay.parquet"),  # demo traffic
    ("data/processed/train.parquet", "data/processed/train.parquet"),    # retraining base sample
    ("data/processed/val.parquet", "data/processed/val.parquet"),        # retraining benchmark
    ("data/warehouse.db", "data/warehouse.db"),               # DWM warehouse (shown only when switched on)
]
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info")


def main():
    if not (ROOT / "frontend/dist/index.html").exists():
        raise SystemExit("frontend/dist is missing: run `npm run build` in frontend/ first")
    if OUT.exists():
        shutil.rmtree(OUT)
    for src, dst in ITEMS:
        s, d = ROOT / src, OUT / dst
        if not s.exists():
            raise SystemExit(f"missing: {src}")
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(s, d, ignore=SKIP)
        else:
            shutil.copy2(s, d)
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    files = sum(1 for f in OUT.rglob("*") if f.is_file())
    print(f"build/space ready: {files} files, {size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
