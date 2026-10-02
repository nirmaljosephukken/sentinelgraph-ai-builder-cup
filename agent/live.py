"""
Live alert stream: alerts in, investigated cases out.

    producer (dispute intake page, bank feed replay)  --publish-->  Pub/Sub topic `fraud-alerts`
    Pub/Sub push subscription  -->  Cloud Run worker (worker/app.py)  -->  process(): run the investigation
    every stage is written to Firestore (`live_alerts`), which the console's Live queue page reads

LIVE_BACKEND=gcp   Pub/Sub + Firestore (Cloud Run)
LIVE_BACKEND=local (default) an in-process thread + JSON files in data/live/, same code path, no cloud needed
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.config import ROOT, SETTINGS

MODE = os.getenv("LIVE_BACKEND", "local").lower()
TOPIC = os.getenv("PUBSUB_TOPIC", "fraud-alerts")
COLLECTION = os.getenv("FIRESTORE_COLLECTION", "live_alerts")
LOCAL_DIR = Path(os.getenv("LIVE_DIR", ROOT / "data" / "live"))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------- stores
class LocalStore:
    def __init__(self, d: Path = LOCAL_DIR):
        self.d = d
        self.d.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def put(self, alert_id: str, fields: dict) -> None:
        with self._lock:
            p = self.d / f"{alert_id}.json"
            doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            doc.update(fields)
            p.write_text(json.dumps(doc, default=str), encoding="utf-8")

    def get(self, alert_id: str) -> dict | None:
        p = self.d / f"{alert_id}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def recent(self, limit: int = 30) -> list[dict]:
        docs = [json.loads(p.read_text(encoding="utf-8")) for p in self.d.glob("*.json")]
        return sorted(docs, key=lambda d: d.get("received_at", ""), reverse=True)[:limit]


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore
        self.db = firestore.Client(project=SETTINGS.gcp_project or None)
        self.col = self.db.collection(COLLECTION)

    def put(self, alert_id: str, fields: dict) -> None:
        # answers and traces are stored as JSON text: compact, and free of Firestore's nesting limits
        self.col.document(alert_id).set(fields, merge=True)

    def get(self, alert_id: str) -> dict | None:
        s = self.col.document(alert_id).get()
        return s.to_dict() if s.exists else None

    def recent(self, limit: int = 30) -> list[dict]:
        from google.cloud import firestore
        q = self.col.order_by("received_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [d.to_dict() for d in q.stream()]


_store = None


def store():
    global _store
    if _store is None:
        _store = FirestoreStore() if MODE == "gcp" else LocalStore()
    return _store


# ---------------------------------------------------------------------------------------------- publish
def publish(alert: dict, source: str) -> str:
    """Queue an alert. Returns its id. The worker picks it up from Pub/Sub (or a local thread)."""
    aid = alert["case_id"]
    store().put(aid, {"alert_id": aid, "status": "queued", "source": source, "received_at": now(),
                      "alert": json.dumps(alert), "case_id": aid, "txn_id": alert["flagged_txn_id"],
                      "card_id": alert["card_id"], "trigger": alert["trigger_type"],
                      "trigger_text": alert["trigger_text"][:300]})
    if MODE == "gcp":
        from google.cloud import pubsub_v1
        pub = pubsub_v1.PublisherClient()
        path = pub.topic_path(SETTINGS.gcp_project, TOPIC)
        msg_id = pub.publish(path, json.dumps(alert).encode("utf-8"), source=source, alert_id=aid).result(timeout=30)
        store().put(aid, {"pubsub_message_id": msg_id})
    else:
        threading.Thread(target=process, args=(alert,), daemon=True).start()
    return aid


# ---------------------------------------------------------------------------------------------- worker job
_backend = None
_run_lock = threading.Lock()  # one investigation at a time per process (the MCP session is shared)


def _graph():
    global _backend
    if _backend is None:
        from agent.backends import get_backend
        _backend = get_backend(SETTINGS)
    return _backend


def use_backend(g) -> None:
    global _backend
    _backend = g


def process(alert: dict) -> dict:
    """Investigate one alert and record every stage. Safe to call twice for the same alert (Pub/Sub may redeliver)."""
    from agent.llm import LLM
    from agent.orchestrator import Investigation
    st = store()
    aid = alert["case_id"]
    doc = st.get(aid) or {}
    if doc.get("status") == "done":
        return doc
    if not doc:
        st.put(aid, {"alert_id": aid, "status": "queued", "source": "pubsub", "received_at": now(),
                     "alert": json.dumps(alert), "case_id": aid, "txn_id": alert["flagged_txn_id"],
                     "card_id": alert["card_id"], "trigger": alert["trigger_type"],
                     "trigger_text": alert["trigger_text"][:300]})
    t0 = time.time()
    st.put(aid, {"status": "investigating", "started_at": now(), "steps": 0})
    steps = {"n": 0}

    def emit(ev):  # light progress updates for the queue page
        steps["n"] += 1
        if ev["kind"] in ("tool", "decision", "memory") and steps["n"] % 3 == 0:
            st.put(aid, {"steps": steps["n"], "last_step": str(ev.get("title", ""))[:160]})

    try:
        with _run_lock:
            inv = Investigation(_graph(), LLM(SETTINGS), alert, emit=emit, use_llm_investigator=False)
            ans = inv.run()
        c = ans["case"]
        fields = {"status": "done", "finished_at": now(), "seconds": round(time.time() - t0, 1),
                  "verdict": c["verdict"], "fraud_probability": c["fraud_probability"], "pattern": c["pattern"],
                  "exposure_usd": c["exposure_usd"], "case_status": c["status"],
                  "final_actions": [f"{a['action']} ({a['route']})" for a in ans["next_best_actions"]["final"]],
                  "sar": bool(ans["sar"]["file"]), "graph_case_id": c["graph_case_id"],
                  "written_to_graph": c["written_to_graph"], "graph_calls": ans["tool_calls"],
                  "answer": json.dumps(ans, default=str), "events": json.dumps(inv.events, default=str)}
        st.put(aid, fields)
        return fields
    except Exception as e:  # recorded, not raised: a failed alert should not be redelivered forever
        st.put(aid, {"status": "error", "finished_at": now(), "error": f"{type(e).__name__}: {str(e)[:300]}"})
        return {"status": "error"}


def bank_feed(n: int = 3, offset: int = 0) -> list[dict]:
    """A few alerts from the benchmark pack, as the bank's own alerting system would send them."""
    import csv
    with open(SETTINGS.prepared_dir / "case_pack.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows[offset: offset + n]:
        a = dict(r)
        a["case_id"] = f"FEED-{r['case_id'].split('-')[1]}-{int(time.time()) % 10000:04d}"
        out.append(a)
    return out
