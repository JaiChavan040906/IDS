"""Stage 9 - Knowledge Repository search and similar-incident retrieval.

Similarity = cosine similarity between CNN-LSTM embeddings of the flows.
Embeddings from different model versions are not comparable, so KR embeddings
are recomputed from the stored raw features with the ACTIVE model and cached
per model version.
"""

import threading

import numpy as np
from sqlalchemy import or_

from ids.api.db import Alert, KREntry


class KnowledgeRepository:
    def __init__(self, models):
        self.models = models
        self._lock = threading.Lock()
        self._cache = {"version": None, "ids": [], "emb": np.zeros((0, 128), "float32")}

    def _embeddings(self, db):
        version = self.models.version
        rows = (db.query(KREntry.id, Alert.features).join(Alert, Alert.id == KREntry.alert_id)
                .order_by(KREntry.id).all())
        ids = [r[0] for r in rows]
        with self._lock:
            c = self._cache
            if c["version"] != version or c["ids"] != ids[:len(c["ids"])]:
                c.update(version=version, ids=[], emb=np.zeros((0, 128), "float32"))
            new = rows[len(c["ids"]):]
            if new:
                e = self.models.embed([r[1] for r in new])
                c["emb"] = np.concatenate([c["emb"], e])
                c["ids"] = c["ids"] + [r[0] for r in new]
            return list(c["ids"]), c["emb"].copy()

    def similar(self, db, features: dict, k: int = 5, exclude_alert: int | None = None):
        ids, emb = self._embeddings(db)
        if not ids:
            return []
        q = self.models.embed([features])[0]
        sims = emb @ q / (np.linalg.norm(emb, axis=1) * np.linalg.norm(q) + 1e-9)
        entries = {e.id: e for e in db.query(KREntry).filter(KREntry.id.in_(ids))}
        out = []
        for i in np.argsort(-sims):
            e = entries[ids[i]]
            if exclude_alert is not None and e.alert_id == exclude_alert:
                continue
            out.append((e, float(sims[i])))
            if len(out) == k:
                break
        return out

    @staticmethod
    def search(db, q: str = "", attack_class: str | None = None, verdict: str | None = None,
               verified: bool | None = None, limit: int = 50):
        query = db.query(KREntry)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(KREntry.title.ilike(like), KREntry.text.ilike(like),
                                     KREntry.attack_class.ilike(like)))
        if attack_class:
            query = query.filter(KREntry.attack_class == attack_class)
        if verdict:
            query = query.filter(KREntry.verdict == verdict)
        if verified is not None:
            query = query.filter(KREntry.verified == verified)
        return query.order_by(KREntry.created_at.desc()).limit(limit).all()
