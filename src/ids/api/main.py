"""FastAPI app: API under /api, the built React frontend under /.

Run:
    .venv/Scripts/python -m uvicorn ids.api.main:app --port 8000
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ids.api.db import ModelVersion, SessionLocal, User, audit, init_db
from ids.api.routers import admin, analyst, auth
from ids.api.security import hash_password
from ids.api.services.kr import KnowledgeRepository
from ids.api.services.model_service import ModelService
from ids.api.services.replay import ReplayService
from ids.api.services.retrain import RetrainService
from ids.data import load_config

APP_CONFIG = os.environ.get("IDS_APP_CONFIG", "configs/app.yaml")
FRONTEND = Path("frontend/dist")


def bootstrap(db, cfg):
    """First start: demo users + register the initial bundle as the active model."""
    for u in cfg["demo_users"]:
        if not db.query(User).filter_by(username=u["username"]).count():
            db.add(User(username=u["username"], full_name=u["full_name"], role=u["role"],
                        password_hash=hash_password(u["password"])))
    if not db.query(ModelVersion).count():
        path = Path(cfg["bundle_dir"]) / cfg["initial_bundle"]
        manifest = json.loads((path / "manifest.json").read_text())
        db.add(ModelVersion(version=cfg["initial_bundle"], path=str(path), status="active",
                            metrics={"benchmark": manifest.get("val_metrics"),
                                     "routing": manifest.get("routing")},
                            notes="Initial model (Stage 5 bundle)", decided_by="system"))
        audit(db, "system", "model.register", cfg["initial_bundle"])
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = yaml.safe_load(open(APP_CONFIG, encoding="utf-8"))
    init_db()
    db = SessionLocal()
    try:
        bootstrap(db, cfg)
        models = ModelService(cfg["bundle_dir"])
        models.load_active(db)
    finally:
        db.close()
    ucfg = yaml.safe_load(open("configs/uncertainty.yaml", encoding="utf-8"))
    app.state.cfg = cfg
    app.state.models = models
    app.state.kr = KnowledgeRepository(models)
    app.state.replay = ReplayService(cfg["replay_file"], models, cfg)
    app.state.retrain = RetrainService(models, cfg, load_config(), ucfg)
    yield
    app.state.replay.stop()


app = FastAPI(title="HITL IDS", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(analyst.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"ok": True, "model": app.state.models.version}


@app.get("/api/public/summary")
def public_summary():
    """Headline numbers for the About page (no login, no sensitive data)."""
    m = app.state.models.detector.manifest
    return {"model_version": m["version"], "metrics": m.get("val_metrics"),
            "routing": m.get("routing"), "classes": app.state.models.detector.enc.classes}


if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = FRONTEND / path
        if path and f.is_file():
            return FileResponse(f)
        # index.html must never be cached, or a rebuilt frontend is not picked up
        return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})
