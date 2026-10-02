"""
SentinelGraph — agentic fraud investigation & next-best action console (TigerGraph × HH Goa 2026, Task 4).

    python -m streamlit run ui/app.py

Less dashboard, more investigation: the first screen answers four questions (what happened, what the agent
found, how certain it is, what happens next); everything below it is the proof. Nothing in the UI changes a
decision; decisions come from agent/policy.py and are read from the answer file and the investigation trace.
"""
from __future__ import annotations

import html as H
import json
import math
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.backends import get_backend  # noqa: E402
from agent.config import SETTINGS  # noqa: E402
from agent.embeddings import embed  # noqa: E402
from agent.llm import LLM  # noqa: E402
from agent.orchestrator import Investigation  # noqa: E402
from ui import viewmodel as vm  # noqa: E402
from ui.theme import CSS  # noqa: E402

ASSETS = ROOT / "ui" / "assets"
st.set_page_config(page_title="SentinelGraph · Fraud Intelligence", page_icon=str(ASSETS / "mark.svg"), layout="wide",
                   initial_sidebar_state="expanded")
st.html(CSS)
st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "mark.svg"), size="large")

KIND = {"trigger": ("Alert received", "#F2C94C"), "case": ("Case opened", "#F2C94C"), "tool": ("Graph query", "#3FA66B"),
        "evidence": ("Evidence", "#C8D4C2"), "assess": ("Assessment", "#F2C94C"), "decision": ("Decision", "#F2C94C"),
        "execute": ("Executed", "#79D9A0"), "request": ("Evidence request", "#A9C8FF"),
        "response": ("Reply", "#A9C8FF"), "llm": ("LLM", "#A9C8FF"), "memory": ("Case memory", "#79D9A0"),
        "guardrail": ("Guardrail", "#FF5C93"), "error": ("Error", "#FF5C93"), "approval": ("Approval", "#79D9A0")}
BADGE_CLS = {"TIGERGRAPH": "tg", "CASE MEMORY": "mem", "MEMORY MODEL": "mem", "GRAPHRAG": "rag", "CUSTOMER": "cust"}
GLYPH = {"BLOCK_ALL_CARDS": ("■", "crit"), "BLOCK_CARD": ("■", "crit"), "DECLINE_TRANSACTION": ("✕", "crit"),
         "STEP_UP_AUTH": ("⇡", "warn"), "VERIFY_WITH_CUSTOMER": ("?", "warn"), "ESCALATE_TO_ANALYST": ("↑", "warn"),
         "ALLOW_TRANSACTION": ("✓", "legit"), "CLOSE_NO_FRAUD": ("✓", "legit"), "MONITOR_CARD": ("◉", "warn")}
TONE = {"crit": ("var(--pink)", "rgba(255,92,147,.16)"), "warn": ("var(--yellow)", "rgba(242,201,76,.16)"),
        "legit": ("var(--legit)", "rgba(121,217,160,.16)")}
STATUS_CHIP = {"closed_fraud": ("c-crit", "Closed · fraud confirmed"), "closed_legitimate": ("c-legit", "Closed · legitimate"),
               "escalated": ("c-warn", "Escalated · analyst review"), "open": ("c-warn", "Open · in progress"),
               "investigating": ("c-warn", "Investigating")}
OUTCOME = {"fraud": ("Fraud", "var(--pink)"), "legitimate": ("Legitimate", "var(--legit)"),
           "uncertain": ("Uncertain", "var(--yellow)")}
SAR_YES = "<span class='badge cust'>file</span>"
SAR_NO = "<span class='muted'>—</span>"


def e(x) -> str:
    return H.escape(str(x), quote=True)


def pct(p: float) -> str:
    """The one formatter for probabilities, so the same number never shows as 3% on one card and 2.6% on another."""
    p *= 100
    return f"{p:.1f}%"


def money(x: float) -> str:
    return f"${x:,.2f}"


def page_head(eyebrow: str, title: str, sub: str = ""):
    st.html(f"<div class='eyebrow'>{e(eyebrow)}</div><h1 class='page'>{e(title)}</h1>"
            + (f"<div class='sub'>{e(sub)}</div>" if sub else ""))


# =========================================================================== data
@st.cache_resource(show_spinner="Connecting to TigerGraph (a suspended Savanna workspace takes 1-3 minutes to wake) …")
def _backend():
    return get_backend(SETTINGS)


def backend():
    try:
        return _backend()
    except Exception as ex:  # noqa: BLE001
        st.error("TigerGraph is not reachable right now. If your Savanna workspace was idle it is suspended: open the "
                 "Savanna console, resume the workspace (or wait 1-3 minutes), then reload this page. "
                 "Saved investigations below still work.")
        with st.expander("Details"):
            st.code(str(ex)[:600])
        st.stop()


@st.cache_data
def case_pack() -> pd.DataFrame:
    return pd.read_csv(SETTINGS.prepared_dir / "case_pack.csv", dtype=str)


@st.cache_data
def closed_cases() -> pd.DataFrame:
    return pd.read_csv(SETTINGS.prepared_dir / "closed_cases.csv", dtype={"case_id": str})


def load_saved(case_id: str):
    a = SETTINGS.cases_dir / f"{case_id}.json"
    t = SETTINGS.traces_dir / f"{case_id}.json"
    if a.exists() and t.exists():
        return json.loads(a.read_text()), json.loads(t.read_text())["events"]
    return None, None


def all_answers() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(SETTINGS.cases_dir.glob("HHG-*.json"))]


def all_traces() -> dict[str, list]:
    out = {}
    for p in sorted(SETTINGS.traces_dir.glob("HHG-*.json")):
        try:
            out[p.stem] = json.loads(p.read_text())["events"]
        except (json.JSONDecodeError, KeyError):
            pass
    return out


@st.cache_data(ttl=120, show_spinner=False)
def status_info():
    """Connection facts for the sidebar; never raises."""
    try:
        g = _backend()
        stats = g.graph_stats()
        via = "MCP" if getattr(g, "mcp", None) is not None else ("RESTPP" if g.name == "tigergraph" else "local")
        ntools = len(g.mcp.tools) if getattr(g, "mcp", None) is not None else 0
        return {"ok": True, "name": g.name, "via": via, "tools": ntools, **stats}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "err": str(ex)}


# =========================================================================== shared pieces
def merged_evidence(answer: dict, events: list[dict]) -> list[dict]:
    raw = []
    for ev in events:
        if ev["kind"] == "evidence" and isinstance(ev.get("detail"), list):
            raw = ev["detail"]
    by_claim = {r["claim"]: r for r in raw}
    out = []
    for item in answer["case"]["evidence"]:
        r = by_claim.get(item["claim"], {})
        direction = r.get("direction")
        if not direction:
            cl = item["claim"].lower()
            direction = "neutral"
            if item["source"] == "customer" and "simulated reply" in cl:
                direction = "fraud" if "denied" in cl else ("legit" if "confirmed" in cl else "neutral")
        out.append({**item, "direction": direction, "lr": r.get("lr"), "family": r.get("family", "context")})
    return out


def trigger_facts(events: list[dict], answer: dict) -> dict:
    trig = next((x for x in events if x["kind"] == "trigger"), {})
    title = trig.get("title", "")
    m = re.search(r"\(\$([\d,]+\.\d\d),\s*([a-z ]+)\)", title)
    amount = float(m.group(1).replace(",", "")) if m else answer["case"]["exposure_usd"]
    channel = m.group(2).strip() if m else ""
    return {"title": title, "amount": amount, "channel": channel, **(trig.get("detail") or {})}


def graph_html(answer: dict, events: list[dict], height: int = 520) -> tuple[str, Counter]:
    c = answer["case"]
    det = trigger_facts(events, answer)
    card, cust, flag = det.get("card_id"), det.get("customer_id"), det.get("flagged_txn_id")
    gid = c["graph_case_id"]
    nodes, edges, cnt = [], [], Counter()

    def n(i, label, group, title=""):
        if i and all(x["id"] != i for x in nodes):
            nodes.append({"id": i, "label": label, "group": group, "title": title or label})
            cnt[group] += 1

    n(cust, cust, "customer", "customer")
    n(card, card, "card", "card under investigation")
    edges.append({"from": cust, "to": card})
    n(gid, gid, "case", f"agent case · {c['verdict']}")
    edges.append({"from": gid, "to": card, "dashes": True})
    for t in c["affected_txn_ids"] or [flag]:
        n(t, t, "flagged" if t == flag else "txn", "flagged transaction" if t == flag else "transaction in the episode")
        edges.append({"from": card, "to": t})
    for d in c["connected_device_profiles"]:
        n(d, d[:24] + ("…" if len(d) > 24 else ""), "device", d)
        for t in (c["affected_txn_ids"] or [flag]):
            edges.append({"from": t, "to": d})
        for k in c["connected_card_ids"][:40]:
            n(k, k, "ccard", "connected card")
            edges.append({"from": d, "to": k})
    if not c["connected_device_profiles"]:
        for k in c["connected_card_ids"][:40]:
            n(k, k, "ccard", "connected card")
            edges.append({"from": flag, "to": k, "dashes": True})
    for m in c["similar_prior_cases"]:
        n(m, m, "memory", "closed case used as memory")
        edges.append({"from": gid, "to": m, "dashes": True})
    data = json.dumps({"nodes": nodes, "edges": edges})
    doc = f"""<!doctype html><html><head><style>
body{{margin:0;background:#10241B;font-family:'IBM Plex Sans',system-ui,sans-serif;border-radius:14px;overflow:hidden}}
#g{{width:100%;height:{height}px}}
.lg{{position:absolute;left:14px;bottom:10px;display:flex;flex-wrap:wrap;gap:14px;font:12px system-ui;color:#C8D4C2}}
.lg i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
</style></head><body>
<div id="g"></div>
<div class="lg"><span><i style="background:#FF5C93"></i>flagged transaction</span><span><i style="background:#F2C94C"></i>episode transaction</span>
<span><i style="background:#F4EFE1"></i>card</span><span><i style="background:#79D9A0"></i>customer</span>
<span><i style="background:#A9C8FF"></i>shared device</span><span><i style="background:#2A5040"></i>connected card</span>
<span><i style="background:#3FA66B"></i>closed case (memory)</span><span><i style="background:#F2C94C;border-radius:50%"></i>agent case</span></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"></script>
<script>
const d = {data};
const F = {{color:'#C8D4C2', size:11, face:'IBM Plex Mono, monospace'}};
const groups = {{
 customer:{{shape:'dot',size:11,color:{{background:'#79D9A0',border:'#79D9A0'}},font:F}},
 card:{{shape:'box',color:{{background:'#F4EFE1',border:'#F4EFE1'}},font:{{color:'#17261E',face:'IBM Plex Mono'}},margin:7}},
 flagged:{{shape:'diamond',size:16,color:{{background:'#FF5C93',border:'#FF5C93'}},font:{{color:'#FFB3CC',size:12,face:'IBM Plex Mono'}}}},
 txn:{{shape:'dot',size:8,color:{{background:'#F2C94C',border:'#F2C94C'}},font:F}},
 device:{{shape:'hexagon',size:17,color:{{background:'#A9C8FF',border:'#A9C8FF'}},font:F}},
 ccard:{{shape:'box',color:{{background:'#153024',border:'#2A5040'}},font:{{color:'#C8D4C2',size:10,face:'IBM Plex Mono'}},margin:4}},
 memory:{{shape:'triangle',size:9,color:{{background:'#3FA66B',border:'#3FA66B'}},font:F}},
 case:{{shape:'star',size:16,color:{{background:'#F2C94C',border:'#F2C94C'}},font:{{color:'#F2C94C',size:12,face:'IBM Plex Mono'}}}}}};
const net = new vis.Network(document.getElementById('g'), {{nodes:new vis.DataSet(d.nodes), edges:new vis.DataSet(d.edges)}},
 {{groups, interaction:{{hover:true, zoomView:true}}, physics:{{stabilization:{{iterations:300}}, barnesHut:{{springLength:115, gravitationalConstant:-5200}}}},
   edges:{{color:{{color:'#2A5040',highlight:'#F2C94C',hover:'#F2C94C'}}, width:1.2, smooth:{{type:'continuous'}}}}}});
net.once('stabilizationIterationsDone', () => {{ net.fit({{animation:false}}); net.setOptions({{physics:false}}); }});
setTimeout(() => net.fit(), 1200);
new ResizeObserver(() => {{ net.redraw(); net.fit(); }}).observe(document.getElementById('g'));
</script></body></html>"""
    return doc, cnt


def show_graph(answer, events, height=520):
    doc, cnt = graph_html(answer, events, height)
    c = answer["case"]
    ndev = cnt["device"]
    chips = [f"<span class='chip'>{cnt['flagged'] + cnt['txn']} transaction(s)</span>",
             f"<span class='chip'>{1 + cnt['ccard']} card(s)</span>",
             f"<span class='chip'>{ndev} shared device{'' if ndev == 1 else 's'}</span>",
             f"<span class='chip'>{cnt['memory']} memory case(s)</span>",
             f"<span class='chip c-legit'><span class='d' style='background:var(--legit)'></span>"
             f"{'written to TigerGraph' if c['written_to_graph'] else 'not written'} · {e(c['graph_case_id'])}</span>"]
    st.html(f"<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px'>{''.join(chips)}</div>")
    if hasattr(st, "iframe"):
        st.iframe(doc, height=height + 8)
    else:
        components.html(doc, height=height + 8)


def meter(label: str, value: float, text: str, color: str) -> str:
    return (f"<div class='meter'><div class='top'><span>{e(label)}</span><b>{e(text)}</b></div>"
            f"<div class='track'><div class='fill' style='width:{max(2, min(100, value * 100)):.0f}%;background:{color}'></div></div></div>")


def family_bars(fam: dict) -> str:
    if not fam:
        return "<div class='muted'>No evidence families recorded.</div>"
    rows = sorted(fam.items(), key=lambda kv: -abs(kv[1]))
    m = max(3.0, max(abs(v) for _, v in rows))
    out = []
    for k, v in rows:
        w = max(1.0, 50 * abs(v) / m)
        lr = math.exp(v)
        txt = f"×{lr:.1f}" if lr >= 1 else f"÷{1 / lr:.1f}"
        clr = "var(--pink)" if v >= 0 else "var(--legit)"
        left = 50 if v >= 0 else 50 - w
        out.append(f"<div class='assess'><span class='ink2'>{e(vm.FAMILY.get(k, k))}</span>"
                   f"<div style='position:relative;height:10px;background:#132A20;border-radius:3px'>"
                   f"<div style='position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--line2)'></div>"
                   f"<div class='bar' style='position:absolute;left:{left:.1f}%;width:{w:.1f}%;background:{clr}'></div></div>"
                   f"<span class='x'>{txt}</span></div>")
    return ("".join(out) + "<div style='display:grid;grid-template-columns:170px 1fr 64px;gap:10px;font:11px var(--mono);"
            "color:var(--mute);margin-top:6px'><span></span><div style='display:flex;justify-content:space-between'>"
            "<span>← legitimate</span><span>fraud →</span></div><span></span></div>")


def action_rows(v: vm.View) -> str:
    """Action hierarchy: executed by the agent / waiting for a human / not permitted without more evidence."""
    a = v.answer
    final = a["next_best_actions"]["final"]
    executed = set()
    for ev in v.events:
        if ev["kind"] == "execute" and isinstance(ev.get("detail"), dict):
            executed |= set(ev["detail"].get("executed", []))
    names = {x["action"] for x in final}
    rows = []
    rank = lambda x: vm.ORDER_HEADLINE.index(x["action"]) if x["action"] in vm.ORDER_HEADLINE else 99  # noqa: E731
    for x in sorted(final, key=lambda x: (x["route"] == "auto", rank(x))):
        if x["route"] == "auto":
            icon, col = "✓", "var(--legit)"
            state = "executed" if (x["action"] in executed or not executed) else "queued"
        else:
            icon, col, state = "◆", "var(--yellow)", f"awaiting {x['route']}"
        rows.append(f"<div class='arow'><span style='color:{col};font:700 13px var(--mono)'>{icon}</span>"
                    f"<div><div class='t'>{e(vm.ACTION_TEXT.get(x['action'], x['action']))} "
                    f"<span class='mono muted' style='font-size:11px'>{e(x['action'])}</span></div>"
                    f"<div class='r'>{e(vm.short(x['reason'], 150))}</div></div><span class='s'>{e(state)}</span></div>")
    verdict = a["case"]["verdict"]
    restricted = []
    if not names & {"BLOCK_CARD", "BLOCK_ALL_CARDS"}:
        restricted.append(("BLOCK_CARD", "R1: a block needs fraud probability ≥85% on two independent lines of evidence"
                           if verdict != "uncertain" else "R8: conflicting evidence, the analyst decides before any block"))
    if verdict == "fraud" and "BLOCK_ALL_CARDS" not in names:
        restricted.append(("BLOCK_ALL_CARDS", "R10: needs confirmed fraud on two or more of the customer's cards"))
    for act, why in restricted:
        rows.append(f"<div class='arow' style='opacity:.6'><span style='color:var(--mute);font:700 13px var(--mono)'>⊘</span>"
                    f"<div><div class='t'>{e(vm.ACTION_TEXT[act])} <span class='mono muted' style='font-size:11px'>{e(act)}</span></div>"
                    f"<div class='r'>{e(why)}</div></div><span class='s'>needs more evidence</span></div>")
    return "<div class='alist'>" + "".join(rows) + "</div>"


def governance(v: vm.View) -> str:
    a = v.answer
    final = a["next_best_actions"]["final"]
    auto = [x for x in final if x["route"] == "auto"]
    human = [x for x in final if x["route"] != "auto"]
    top = "L2" if any(x["route"] == "L2" for x in human) else ("L1" if human else "auto")
    rules = sorted({r for x in final for r in re.findall(r"\b(R\d+|3a)\b", x["reason"])},
                   key=lambda r: (r == "3a", int(r[1:]) if r[1:].isdigit() else 0))
    n_audit = sum(1 for ev in v.events if ev["kind"] in ("decision", "execute", "memory", "request", "response"))
    cells = [("Execution", f"{len(auto)} auto · {len(human)} queued for approval"),
             ("Approval route", vm.ROUTE_WHO[top]),
             ("Policy", "Fraud Policy v1.0 · " + (", ".join(rules) if rules else "section 6")),
             ("Audit", f"{n_audit} logged decisions · {a['case']['graph_case_id']}")]
    return "<div class='gov'>" + "".join(f"<div><div class='eyebrow'>{e(k)}</div><div class='v'>{e(val)}</div></div>"
                                         for k, val in cells) + "</div>"


def record_approval(answer, action, decision):
    g = backend()
    ev = {"ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
          "title": f"{action['action']} {decision} by {action['route']} approver", "detail": {"action": action, "decision": decision}}
    try:
        if hasattr(g, "tg"):
            cid = answer["case"]["graph_case_id"]
            eid = f"{cid}#A{int(time.time())}"
            g.tg.upsert(vertices={"CaseEvent": {eid: {"case_id": {"value": cid}, "step": {"value": 99},
                                                     "ts": {"value": ev["ts"]}, "kind": {"value": "approval"},
                                                     "title": {"value": ev["title"]},
                                                     "detail": {"value": json.dumps(ev["detail"])}}}},
                        edges={"FraudCase": {cid: {"FC_EVENT": {"CaseEvent": {eid: {}}}}}})
        st.session_state.setdefault("approvals", []).append({**ev, "case": answer["case_id"]})
        st.toast(f"{ev['title']} · recorded in the case audit trail")
    except Exception as ex:  # noqa: BLE001
        st.error(f"Could not record the approval: {ex}")


# =========================================================================== investigate: sections
def sec(title: str, right: str = ""):
    st.html(f"<div class='sec'><h3>{e(title)}</h3><span class='eyebrow'>{e(right)}</span></div>")


def case_header(case: dict, v: vm.View | None):
    if v is None:
        st.html(f"<div class='eyebrow'>Alert · {e(case['trigger_type'].replace('_', ' '))}</div>"
                f"<h1 class='page'>{e(case['case_id'])}</h1><div class='sub'>{e(case['trigger_text'])}</div>")
        return
    c = v.answer["case"]
    tf = trigger_facts(v.events, v.answer)
    chip_cls, chip_txt = STATUS_CHIP.get(c["status"], ("", c["status"]))
    line = [f"txn {tf.get('flagged_txn_id', case.get('flagged_txn_id', ''))}", money(tf["amount"])]
    if tf["channel"]:
        line.append(tf["channel"])
    line.append(f"card {tf.get('card_id') or case.get('card_id', '')}")
    if v.bank_score is not None:
        line.append(f"bank risk score {v.bank_score:.2f}")
    st.html(f"<div class='head'><div><div class='eyebrow'>Case {e(case['case_id'])} · {e(c['graph_case_id'])} · "
            f"{e(case['trigger_type'].replace('_', ' '))}</div>"
            f"<h1 class='page'>{e(c['pattern'].replace('_', ' ').capitalize())}</h1>"
            f"<div class='line'>{' · '.join(e(x) for x in line)}</div></div>"
            f"<span class='chip {chip_cls}' style='margin-top:8px'><span class='d' style='background:currentColor'></span>"
            f"{e(chip_txt)}</span></div>")


def four_questions(case: dict, v: vm.View, ev_items: list[dict]):
    c = v.answer["case"]
    tf = trigger_facts(v.events, v.answer)
    trig = case["trigger_type"]
    chan = (tf["channel"] + " ") if tf["channel"] else ""
    what = {"risk_score": f"Bank model flagged a {money(tf['amount'])} {chan}payment",
            "customer_report": f"Cardholder disputes a {money(tf['amount'])} charge",
            "analyst_request": "An analyst asked for a review"}.get(trig, "Alert raised")
    find = vm.finding_sentence(v, ev_items)
    f1, _, f2 = find.partition(". ")
    outcome, ocol = OUTCOME.get(c["verdict"], (c["verdict"], "var(--ink)"))
    h = v.headline
    who = vm.ROUTE_WHO.get(h.get("route", "auto"), "")
    n_other = len(v.answer["next_best_actions"]["final"]) - 1
    more = f" · plus {n_other} supporting action{'' if n_other == 1 else 's'}" if n_other > 0 else ""
    thr = " · decision threshold met" if v.final.threshold_met else " · threshold not met"
    st.html(
        "<div class='q4'>"
        f"<div><div class='eyebrow'>What happened?</div><div class='a'>{e(what)}</div>"
        f"<div class='b'>{e(vm.short(case['trigger_text'], 140))}</div></div>"
        f"<div><div class='eyebrow'>What did the agent find?</div><div class='a'>{e(f1.rstrip('.'))}</div>"
        f"<div class='b'>{e(vm.short(f2, 150))}</div></div>"
        f"<div><div class='eyebrow'>How certain is it?</div><div class='a'><span style='color:{ocol}'>{e(outcome)}</span> · "
        f"{e(vm.conf_level(v.final.confidence))} confidence</div>"
        f"<div class='b'>Fraud probability {pct(v.p_final)} · {ev_text(v)[2]}{thr}</div></div>"
        f"<div class='next'><div class='eyebrow'>What happens next?</div>"
        f"<div class='a'>{e(vm.ACTION_TEXT.get(h.get('action'), h.get('action', '—')))}</div>"
        f"<div class='b'>Approval: {e(who)}{e(more)}</div></div>"
        "</div>")


def ev_text(v: vm.View) -> tuple[str, str, str]:
    """(value, label, sentence) for the evidence count; conflicting cases show both sides."""
    f = v.final
    if v.answer["case"]["verdict"] == "uncertain":
        return (f"{f.support} vs {f.contra}", "for fraud vs legitimate · conflicting",
                f"evidence conflicts ({f.support} line(s) for fraud, {f.contra} for legitimate)")
    return (f"{min(f.support, 2)}/2", "independent lines · policy §6",
            f"{min(f.support, 2)}/2 independent lines of evidence agree")


def kpis(v: vm.View):
    c = v.answer["case"]
    risk = vm.risk_level(v.p_final)
    rcol = {"High": "var(--pink)", "Elevated": "var(--pink)", "Moderate": "var(--yellow)", "Low": "var(--legit)"}[risk]
    chip_txt = STATUS_CHIP.get(c["status"], ("", c["status"]))[1]
    head, _, tail = chip_txt.partition(" · ")
    cells = [("Fraud probability", f"<span style='color:{rcol}'>{pct(v.p_final)}</span>", f"{risk} risk · agent posterior"),
             ("Confidence", f"{v.final.confidence * 100:.0f}%", f"{vm.conf_level(v.final.confidence)} · decisive + sufficient"),
             ("Evidence", ev_text(v)[0], ev_text(v)[1]),
             ("Pattern", f"<span style='font:700 16px/1.25 var(--display);white-space:normal'>{e(c['pattern'].replace('_', ' '))}</span>",
              "fraud pattern"),
             ("Exposure", money(c["exposure_usd"]), f"{len(c['affected_txn_ids'])} transaction(s)"),
             ("Case", e(head), e(tail or c["status"]))]
    st.html("<div class='kpis'>" + "".join(
        f"<div class='kpi'><div class='eyebrow'>{k}</div><div class='n' title='{e(re.sub('<[^>]+>', '', n))}'>{n}</div>"
        f"<div class='l'>{lab}</div></div>" for k, n, lab in cells) + "</div>")


def nba_panel(v: vm.View):
    h = v.headline
    act = h.get("action", "")
    glyph, tone = GLYPH.get(act, ("→", "warn"))
    fg, bg = TONE[tone]
    st.html(f"<div class='nba'><div class='eyebrow' style='color:var(--yellow)'>Next best action · recommended</div>"
            f"<div class='big'><span class='ic' style='background:{bg};color:{fg}'>{glyph}</span>"
            f"{e(vm.ACTION_TEXT.get(act, act))}</div>"
            f"<div class='why'>{e(h.get('reason', ''))}</div>"
            f"<div class='eyebrow' style='margin-top:18px'>Action hierarchy</div>{action_rows(v)}"
            f"<div class='eyebrow' style='margin-top:18px'>Action governance</div>{governance(v)}</div>")
    pending = [x for x in v.answer["next_best_actions"]["final"] if x["route"] != "auto"]
    for x in pending:
        k1, k2, k3 = st.columns([5, 1.2, 1.2], vertical_alignment="center")
        k1.html(f"<div class='muted' style='font-size:13px'>Approve <b class='mono' style='color:var(--ink)'>{e(x['action'])}</b> "
                f"as {e(vm.ROUTE_WHO[x['route']])}</div>")
        key = f"{v.answer['case_id']}-{x['action']}"
        if k2.button("Approve", key="ap" + key, type="primary", use_container_width=True):
            record_approval(v.answer, x, "approved")
        if k3.button("Reject", key="rj" + key, use_container_width=True):
            record_approval(v.answer, x, "rejected")


def sufficiency_panel(v: vm.View):
    f = v.final
    title, bullets, closing = vm.why_stopped(v)
    bic, bcol = ("!", "var(--yellow)") if "handed" in title else ("✓", "var(--legit)")
    gaps = "".join(f"<div class='tick'><span class='i' style='color:var(--legit)'>✓</span>{e(g)}</div>" for g in v.gaps_resolved)
    gcol = "var(--mute)" if f.threshold_met else "var(--pink)"
    gaps += "".join(f"<div class='tick'><span class='i' style='color:{gcol}'>?</span>{e(g)}</div>" for g in v.gaps_open[:4])
    thr = ("<span class='chip c-legit'>threshold met</span>" if f.threshold_met
           else "<span class='chip c-warn'>threshold not met</span>")
    st.html(
        f"<div class='panel'><div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<div class='eyebrow'>Evidence sufficiency &amp; uncertainty</div>{thr}</div>"
        + meter("Independent lines of evidence", f.sufficiency,
                f"{f.support} vs {f.contra} · conflicting" if v.answer["case"]["verdict"] == "uncertain" else f"{min(f.support, 2)} of 2 required",
                "var(--legit)" if f.sufficiency >= 1 else "var(--yellow)")
        + meter("Decision confidence", f.confidence, f"{f.confidence * 100:.0f}% · {vm.conf_level(f.confidence)}", "var(--yellow)")
        + meter("Fraud probability", v.p_final, f"{pct(v.p_final)} · stop at ≤15% or ≥85%",
                "var(--pink)" if v.p_final >= 0.5 else "var(--legit)")
        + (f"<div class='eyebrow' style='margin-top:12px'>Open questions at first look</div>{gaps}" if gaps else "")
        + f"<div class='stopbox'><h4>{e(title)}?</h4>"
        + "".join(f"<div class='tick'><span class='i' style='color:{bcol}'>{bic}</span>{e(b)}</div>" for b in bullets)
        + f"<div class='muted' style='font-size:12.5px;margin-top:8px'>{e(closing)}</div></div></div>")


def evolution(v: vm.View):
    a = v.answer
    req = a["evidence_requests"]
    nba = a["next_best_actions"]
    rank = lambda x: vm.ORDER_HEADLINE.index(x["action"]) if x["action"] in vm.ORDER_HEADLINE else 99  # noqa: E731
    i_head = sorted(nba["initial"], key=rank)
    i_act = vm.ACTION_TEXT.get(i_head[0]["action"], i_head[0]["action"]) if i_head else "—"
    f_act = vm.ACTION_TEXT.get(v.headline.get("action"), v.headline.get("action", "—"))

    def stage(eyebrow, p, conf, act, extra="", mid=False):
        return (f"<div class='st{' mid' if mid else ''}'><div class='eyebrow'>{e(eyebrow)}</div>"
                + (f"<div class='row'><span>Fraud probability</span><b>{pct(p)}</b></div>" if p is not None else "")
                + (f"<div class='row'><span>Confidence</span><b>{conf * 100:.0f}%</b></div>" if conf is not None else "")
                + (f"<div class='sact'>{e(act)}</div>" if act else "") + extra + "</div>")

    if req:
        r = req[0]
        sec("Decision evolution", "initial → evidence gathered → final")
        body = (stage("1 · Initial assessment", v.p_initial, v.initial.confidence, i_act)
                + "<div class='arr'>→</div>"
                + stage(f"2 · Evidence gathered · {r['type'].replace('_', ' ')}", None, None, "",
                        f"<div class='reply'>{e(vm.short(r['assumed_response'], 260))}</div>", mid=True)
                + "<div class='arr'>→</div>"
                + stage("3 · Final decision", v.p_final, v.final.confidence, f_act))
        st.html(f"<div class='evo'>{body}</div>"
                f"<div class='decision' style='margin-top:10px'><b style='color:var(--ink)'>What changed · </b>{e(nba['what_changed'])}</div>")
    else:
        sec("Decision evolution", "memory prior → graph evidence → decision")
        body = (stage("1 · Case-memory prior", v.prior, None, "Model score only, before the graph")
                + "<div class='arr'>→</div>"
                + stage("2 · Graph evidence", None, None, "",
                        f"<div class='reply'>{a['tool_calls']} TigerGraph queries via {e(via_text(v.events))} · {v.final.support} independent "
                        f"line(s) agree · no customer contact needed</div>", mid=True)
                + "<div class='arr'>→</div>"
                + stage("3 · Decision", v.p_final, v.final.confidence, f_act))
        st.html(f"<div class='evo'>{body}</div>"
                "<div class='decision' style='margin-top:10px'><b style='color:var(--ink)'>No evidence request · </b>"
                "the graph evidence alone met the policy's stop rule, so the initial and final recommendations in the "
                "answer file are the same action set.</div>")


def evidence_col(items: list[dict]):
    st.html("<div class='layer' style='color:var(--yellow)'><span class='n'>1</span>Evidence · what the graph shows</div>")
    order = {"fraud": 0, "legit": 1}
    out = []
    for x in sorted(items, key=lambda x: (order.get(x["direction"], 2), -abs(math.log(x.get("lr") or 1)))):
        d = x["direction"] if x["direction"] in ("fraud", "legit") else "neutral"
        badge = vm.source_badge(x["ref"], x["source"])
        lr = x.get("lr")
        lrt = ""
        if lr and d != "neutral":
            lrt = f"<span class='lr'>{'×' + format(lr, '.1f') if lr >= 1 else '÷' + format(1 / lr, '.1f')} odds</span>"
        ids = ", ".join(x["entity_ids"][:4]) + ("…" if len(x["entity_ids"]) > 4 else "")
        dirl = {"fraud": "points to fraud", "legit": "points to legitimate", "neutral": "context"}[d]
        out.append(f"<div class='ev {d}'><div class='c'>{e(x['claim'])}</div><div class='m'>"
                   f"<span class='badge {BADGE_CLS.get(badge, '')}'>{e(badge)}</span>"
                   f"<span class='ref'>{e(x['ref'])}{' · ' + e(ids) if ids else ''} · {dirl}</span>{lrt}</div></div>")
    st.html("<div class='evgrid'>" + "".join(out) + "</div>")


def assessment_col(v: vm.View, events: list[dict]):
    af = [x["detail"] for x in events if x["kind"] == "assess" and isinstance(x.get("detail"), dict)]
    fam = (af[-1] if af else {}).get("log_lr_by_family") or {}
    c = v.answer["case"]
    bank = "" if v.bank_score is None else f"; the bank risk score ({v.bank_score:.2f}) is an input, not a verdict"
    st.html("<div class='layer' style='color:var(--legit)'><span class='n'>2</span>Assessment · how the agent weighs it</div>"
            f"<div class='panel' style='height:auto'>{family_bars(fam)}"
            f"<div class='muted' style='font-size:12.5px;margin-top:12px;line-height:1.55'>Each bar is one evidence family's "
            f"likelihood ratio, capped so no single family decides alone. Memory-model prior {pct(v.prior)} → "
            f"fraud probability {pct(v.p_final)}{bank}.</div></div>")
    oname, ocol = OUTCOME.get(c["verdict"], (c["verdict"], "var(--ink)"))
    st.html("<div class='layer' style='color:var(--pink)'><span class='n'>3</span>Decision · investigation outcome</div>"
            f"<div class='decision'><div style='font:700 17px var(--display);color:{ocol}'>"
            f"{e(oname)} · {e(c['status'].replace('_', ' '))}</div>"
            f"<div style='margin-top:6px'>{e(c['summary'])}</div>"
            f"<div style='margin-top:8px' class='muted'><b>Stop reason · </b>{e(v.answer['stop_reason'])}</div></div>")


def activity(events: list[dict]):
    rows = []
    for ev in events:
        label, color = KIND.get(ev["kind"], (ev["kind"], "#8BA293"))
        d = ev.get("detail") or {}
        x = ""
        if ev["kind"] == "tool" and isinstance(d, dict):
            x = f"{str(d.get('transport', '')).upper()} · {float(d.get('latency_s', 0) or 0):.2f}s"
        elif ev["kind"] == "execute" and isinstance(d, dict):
            x = "executed: " + ", ".join(d.get("executed", []))
            if d.get("awaiting"):
                x += "  ·  awaiting: " + ", ".join(d["awaiting"])
        elif ev["kind"] == "decision" and isinstance(d, dict) and d.get("why_request"):
            x = "why ask: " + d["why_request"]
        tm = f"+{float(ev.get('elapsed_s', 0) or 0):.1f}s"
        sub = f"<div class='xx'>{e(vm.short(x, 180))}</div>" if x else ""
        rows.append(f"<div class='act'><div class='tm'>{tm}</div><div class='dt' style='background:{color}'></div>"
                    f"<div><div class='tt'><span class='mono' style='font-size:11px;color:{color};text-transform:uppercase;"
                    f"letter-spacing:.06em'>{e(label)}</span> &nbsp;{e(vm.short(ev['title'], 170))}</div>{sub}</div></div>")
    st.html("<div class='panel' style='height:auto;padding:10px 18px'>" + "".join(rows) + "</div>")


def tab_sar(answer: dict):
    s = answer["sar"]
    if not s["file"]:
        st.html(f"<div class='panel' style='height:auto'><div class='eyebrow'>Suspicious activity report</div>"
                f"<div style='margin-top:6px;font-size:15px;color:var(--ink)'>Not required.</div>"
                f"<div class='muted' style='margin-top:6px;font-size:13.5px'>{e(s['reason'])}</div></div>")
        return
    subj = e(", ".join(s["subjects"][:10])) + (" …" if len(s["subjects"]) > 10 else "")
    st.html(f"<div class='sar'><div class='hd'><div><div class='eyebrow'>Suspicious activity report · draft for L2 approval</div>"
            f"<div style='font:700 18px var(--display);margin-top:2px'>{e(answer['case']['graph_case_id'])}</div></div>"
            f"<span class='badge' style='background:#FFD9E6;color:#8A1740;border-color:#F5B4CB'>FILE_REPORT · L2</span></div>"
            f"<div class='grid'><div><div class='eyebrow'>Amount</div><div class='mono'>{money(s['total_amount_usd'])}</div></div>"
            f"<div><div class='eyebrow'>Activity dates</div><div class='mono'>{e(' → '.join(s['activity_dates']))}</div></div>"
            f"<div><div class='eyebrow'>Subjects</div><div class='mono' style='font-size:12px'>{subj}</div></div></div>"
            f"<div class='body'>{e(s['narrative'])}</div>"
            f"<div class='body' style='border-top:1px solid var(--cream-line);font-size:13px;color:var(--cream-mute)'>"
            f"<b>Basis · </b>{e(s['reason'])}</div></div>")


def memory_card(cid: str, r: dict | None, score: float | None = None) -> str:
    if r is None:
        return f"<div class='ev neutral'><div class='c mono'>{e(cid)}</div></div>"
    oc = str(r.get("outcome", ""))
    exp = r.get("exposure_usd")
    exp_t = f" · {money(float(exp))}" if exp not in (None, "") and not (isinstance(exp, float) and math.isnan(exp)) else ""
    sim = f"<span class='lr'>similarity {score:.2f}</span>" if score is not None else ""
    tgb = "<span class='badge tg'>TIGERGRAPH VECTOR</span>" if score is not None else ""
    return (f"<div class='ev {'fraud' if 'fraud' in oc else 'legit'}'><div class='c'><b class='mono'>{e(cid)}</b> · "
            f"{e(str(r.get('pattern', '')).replace('_', ' '))} · {e(oc.replace('_', ' '))}{exp_t}</div>"
            f"<div class='m'><span class='badge mem'>CASE MEMORY</span>{tgb}"
            f"<span class='ref'>{e(vm.short(str(r.get('analyst_notes') or r.get('notes') or ''), 220))}</span>{sim}</div></div>")


def tab_memory(answer: dict, items: list[dict]):
    c = answer["case"]
    mem = next((x for x in items if x["claim"].startswith("Case memory")), None)
    cc = closed_cases().set_index("case_id")
    cards = [memory_card(m, cc.loc[m].to_dict() if m in cc.index else None) for m in c["similar_prior_cases"]]
    st.html("<div class='eyebrow' style='margin-bottom:8px'>Closed cases retrieved as memory · graph adjacency + TigerGraph vector search</div>"
            + (f"<div class='decision' style='margin-bottom:10px'>{e(mem['claim'])}</div>" if mem else "")
            + "<div class='evgrid'>" + "".join(cards) + "</div>")
    if c["pattern_description"]:
        st.html(f"<div class='eyebrow' style='margin-top:18px'>Undocumented pattern</div>"
                f"<div class='decision' style='margin-top:8px'>{e(c['pattern_description'])}</div>")


def show_investigation(case: dict, answer: dict, events: list[dict]):
    v = vm.build(case, answer, events)
    items = merged_evidence(answer, events)
    case_header(case, v)
    four_questions(case, v, items)
    kpis(v)
    left, right = st.columns([1.55, 1], gap="medium")
    with left:
        nba_panel(v)
    with right:
        sufficiency_panel(v)
    evolution(v)
    sec("Investigation graph", "TigerGraph · FraudGraph · drag, zoom, hover")
    show_graph(answer, events)
    sec("Evidence → Assessment → Decision", "kept separate on purpose")
    c1, c2 = st.columns([1.2, 1], gap="medium")
    with c1:
        evidence_col(items)
    with c2:
        assessment_col(v, events)
    sec("Agent activity", f"{answer['tool_calls']} graph calls · {answer['latency_s']}s · {len(events)} steps")
    activity(events)
    st.html("<div style='height:8px'></div>")
    tabs = st.tabs(["Suspicious activity report", "Case memory", "Answer file", "Raw trace"])
    with tabs[0]:
        tab_sar(answer)
    with tabs[1]:
        tab_memory(answer, items)
    with tabs[2]:
        st.download_button("Download answer file", json.dumps(answer, indent=2), file_name=f"{answer['case_id']}.json")
        st.json(answer, expanded=1)
    with tabs[3]:
        st.json(events, expanded=False)
    st.html("<div class='muted' style='font-size:12px;margin-top:22px;line-height:1.6;border-top:1px solid var(--line);padding-top:12px'>"
            "<b>Definitions.</b> <b>Fraud probability</b>: the agent's posterior after fusing all evidence (the answer file "
            "rounds it to two decimals). <b>Memory-model prior</b>: the case-memory model's calibrated fraud rate before "
            "graph evidence. <b>Bank risk score</b>: the bank's alerting score, an input only. <b>Confidence</b>: half how "
            "decisive the probability is, half whether two independent lines of evidence agree.</div>")


# =========================================================================== pages
def saved_time(case_id: str) -> str:
    p = SETTINGS.cases_dir / f"{case_id}.json"
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%d %b %Y, %H:%M") if p.exists() else ""


def via_text(events: list | None) -> str:
    ts = Counter(str((ev.get("detail") or {}).get("transport", "")).upper() for ev in (events or [])
                 if ev.get("kind") == "tool" and isinstance(ev.get("detail"), dict))
    ts.pop("", None)
    return " + ".join(ts) if ts else "TigerGraph"


def run_banner(kind: str, answer: dict, when: str, events: list | None = None):
    if kind == "live":
        st.html(f"<div class='runbar live'><span class='chip c-legit'><span class='d' style='background:var(--legit)'></span>"
                f"Live run</span><span>{e(when)} · {answer['tool_calls']} TigerGraph calls via {e(via_text(events))} · {answer['latency_s']}s · "
                f"written to the graph as {e(answer['case']['graph_case_id'])}</span></div>")
    else:
        st.html(f"<div class='runbar'><span class='chip'>Saved investigation</span><span>last run {e(when)} · "
                f"{answer['tool_calls']} TigerGraph calls · {answer['latency_s']}s · opened from the case portfolio</span></div>")


def compare_strip(prev: dict | None, new: dict):
    """What changed between the previous saved run and this live run, so an identical outcome still reads as re-run."""
    if not prev:
        st.html("<div class='cmp'><b>First run for this alert.</b> No earlier investigation to compare with.</div>")
        return
    a, b = prev["case"], new["case"]
    pa = {x["action"] for x in prev["next_best_actions"]["final"]}
    pb = {x["action"] for x in new["next_best_actions"]["final"]}
    items = []
    same = a["verdict"] == b["verdict"]
    items.append(("Outcome", f"unchanged ({b['verdict']})" if same else f"{a['verdict']} → {b['verdict']}", same))
    dp = abs(a["fraud_probability"] - b["fraud_probability"]) < 0.005
    items.append(("Fraud probability", f"{pct(a['fraud_probability'])} → {pct(b['fraud_probability'])}", dp))
    if pa == pb:
        items.append(("Actions", "unchanged", True))
    else:
        ch = [f"+{x}" for x in sorted(pb - pa)] + [f"−{x}" for x in sorted(pa - pb)]
        items.append(("Actions", ", ".join(ch), False))
    ev_a, ev_b = len(a["evidence"]), len(b["evidence"])
    items.append(("Evidence", f"{ev_a} → {ev_b} findings", ev_a == ev_b))
    items.append(("Narrative", "rewritten" if a["summary"] != b["summary"] else "identical", True))
    items.append(("Graph calls", f"{prev['tool_calls']} → {new['tool_calls']}", True))
    cells = "".join(f"<div><div class='eyebrow'>{e(k)}</div><div class='v' style='color:{'var(--ink)' if ok else 'var(--yellow)'}'>"
                    f"{e(v)}</div></div>" for k, v, ok in items)
    note = ("Same evidence in the graph, same policy, so the same decision. The agent is deterministic by design; "
            "only the LLM's wording and the timings move.") if same and pa == pb else \
        "The decision moved. Highlighted cells show what changed since the previous run."
    st.html(f"<div class='cmp'><div class='eyebrow' style='color:var(--yellow);margin-bottom:8px'>Compared with the previous run</div>"
            f"<div class='cmpgrid'>{cells}</div><div class='muted' style='font-size:12.5px;margin-top:8px'>{e(note)}</div></div>")


def alert_preview(case: dict):
    trig = {"risk_score": "Bank risk score", "customer_report": "Customer report",
            "analyst_request": "Analyst request"}.get(case["trigger_type"], case["trigger_type"])
    rs = case.get("risk_score") or ""
    cells = [("Trigger", trig), ("Opened", case.get("opened_at", "")), ("Transaction", case.get("flagged_txn_id", "")),
             ("Card", case.get("card_id") or "resolved by the agent")]
    if rs:
        cells.append(("Bank score", rs))
    st.html(f"<div class='eyebrow'>Incoming alert · not yet investigated in this session</div>"
            f"<h1 class='page'>{e(case['case_id'])}</h1>"
            f"<div class='alertcard'><div class='quote'>“{e(case['trigger_text'])}”</div>"
            f"<div class='gov' style='grid-template-columns:repeat({len(cells)},1fr);margin-top:14px'>"
            + "".join(f"<div><div class='eyebrow'>{e(k)}</div><div class='v mono'>{e(v)}</div></div>" for k, v in cells)
            + "</div></div>"
            "<div class='empty' style='margin-top:18px'><div style='font:400 30px var(--serif);color:var(--yellow);"
            "text-transform:uppercase'>Ready to investigate</div><div style='margin-top:6px'>Press <b>Run investigation</b>. "
            "The agent will query TigerGraph through MCP, weigh the evidence, decide the next best action and write "
            "the case to the graph. Past results live in the <a href='./portfolio' target='_self' style='color:var(--yellow)'>"
            "Case Portfolio</a>.</div></div>")


def page_investigate():
    pack = case_pack()
    qp = st.query_params.get("case", "")
    saved_view = st.query_params.get("view", "") == "saved"
    icon = {"risk_score": "bank score", "customer_report": "customer dispute", "analyst_request": "analyst request"}
    opts = [f"{r.case_id}  ·  {icon.get(r.trigger_type, r.trigger_type)}  ·  txn {r.flagged_txn_id}" for r in pack.itertuples()]
    idx = next((i for i, o in enumerate(opts) if o.startswith(qp)), 0) if qp else 0
    llm_probe = LLM(SETTINGS)
    t1, t2, t3, t4 = st.columns([3.2, 1.3, 1.4, 1.2], vertical_alignment="center")
    choice = t1.selectbox("Alert", opts, index=idx, label_visibility="collapsed")
    use_llm = t2.toggle("LLM investigator", value=llm_probe.provider != "none",
                        help="Off = deterministic narrative templates. Graph work and decisions are identical.")
    run = t3.button("Re-run live" if saved_view else "Run investigation", type="primary", use_container_width=True,
                    icon=":material/play_arrow:")
    with t4.popover("Custom alert", use_container_width=True):
        c_txn = st.text_input("Transaction ID", "3503988")
        c_trig = st.selectbox("Trigger", ["risk_score", "customer_report", "analyst_request"])
        c_text = st.text_area("Trigger text", "Analyst request: review this transaction and related activity.")
        run_custom = st.button("Investigate custom alert", use_container_width=True)
    cid = choice.split()[0]
    case = pack[pack.case_id == cid].iloc[0].to_dict()
    if cid != qp:  # a different alert was picked: leave the saved view
        st.query_params.clear()
        st.query_params["case"] = cid
        saved_view = False
    if run_custom:
        ctx = backend().txn_context(c_txn)["txn"]
        case = {"case_id": f"ADHOC-{c_txn[-3:]}", "opened_at": ctx["ts"][:10] + " 23:59:00", "trigger_type": c_trig,
                "trigger_text": c_text, "flagged_txn_id": c_txn, "card_id": ctx["card_id"],
                "customer_id": ctx["customer_id"], "risk_score": ""}
        run = True
    if run:
        if not use_llm:
            SETTINGS.llm_provider = "none"
        prev, _ = load_saved(case["case_id"])
        g = backend()
        llm = LLM(SETTINGS)
        box = st.status("Agent investigating on TigerGraph …", expanded=True)

        def emit(ev):
            label, color = KIND.get(ev["kind"], (ev["kind"], "#8BA293"))
            d = ev.get("detail") or {}
            x = f"{str(d.get('transport', '')).upper()} · {float(d.get('latency_s', 0) or 0):.2f}s" \
                if ev["kind"] == "tool" and isinstance(d, dict) else ""
            box.html(f"<div class='lv'><div class='k' style='color:{color}'>{e(label)}</div>"
                     f"<div>{e(vm.short(ev['title'], 150))}</div><div class='x'>{x}</div></div>")

        inv = Investigation(g, llm, case, emit=emit, use_llm_investigator=use_llm)
        answer = inv.run()
        box.update(label=f"Investigation complete · {answer['tool_calls']} graph calls · {answer['latency_s']}s",
                   state="complete", expanded=False)
        when = datetime.now().strftime("%d %b %Y, %H:%M:%S")
        st.session_state["result"] = (case, answer, inv.events)
        st.session_state["live"] = {"case_id": case["case_id"], "when": when, "prev": prev}
        if case["case_id"].startswith("HHG-"):
            (SETTINGS.cases_dir / f"{case['case_id']}.json").write_text(json.dumps(answer, indent=2))
            (SETTINGS.traces_dir / f"{case['case_id']}.json").write_text(json.dumps(
                {"case": case, "events": inv.events, "llm": {"provider": llm.provider, "model": llm.model}},
                indent=1, default=str))
        if saved_view:
            st.query_params.pop("view", None)
        run_banner("live", answer, when, inv.events)
        compare_strip(prev, answer)
        show_investigation(case, answer, inv.events)
        return
    live = st.session_state.get("live")
    res = st.session_state.get("result")
    if live and res and live["case_id"] == case["case_id"] and res[1]["case_id"] == case["case_id"] and not saved_view:
        # a live run from this session (e.g. after pressing Approve): keep showing it
        run_banner("live", res[1], live["when"], res[2])
        compare_strip(live["prev"], res[1])
        show_investigation(*res)
        return
    if saved_view:
        a, ev = load_saved(case["case_id"])
        if a:
            st.session_state["result"] = (case, a, ev)
            run_banner("saved", a, saved_time(case["case_id"]))
            show_investigation(case, a, ev)
            return
    alert_preview(case)


def page_portfolio():
    data = all_answers()
    page_head("Investigations", "Case portfolio", "Twenty benchmark alerts, each investigated end to end and written to TigerGraph.")
    if not data:
        st.html("<div class='empty'>No answer files yet. Run the agent on a case.</div>")
        return
    cnt = Counter(a["case"]["verdict"] for a in data)
    sars = sum(1 for a in data if a["sar"]["file"])
    exp = sum(a["case"]["exposure_usd"] for a in data if a["case"]["verdict"] == "fraud")
    pend = sum(1 for a in data for x in a["next_best_actions"]["final"] if x["route"] != "auto")
    cells = [("Cases", len(data), ""), ("Fraud", cnt["fraud"], "var(--pink)"), ("Legitimate", cnt["legitimate"], "var(--legit)"),
             ("Uncertain", cnt["uncertain"], "var(--yellow)"), ("SARs drafted", sars, ""), ("Awaiting approval", pend, "var(--yellow)")]
    st.html("<div class='kpis'>" + "".join(f"<div class='kpi'><div class='eyebrow'>{k}</div><div class='n' style='color:{c or 'var(--ink)'}'>"
                                           f"{n}</div></div>" for k, n, c in cells) + "</div>"
            f"<div class='muted' style='font-size:13px;margin:-4px 0 12px'>Fraud exposure identified: "
            f"<b class='mono' style='color:var(--ink)'>{money(exp)}</b></div>")
    rows = []
    traces = all_traces()
    pack = case_pack().set_index("case_id")
    for a in data:
        c = a["case"]
        ev = traces.get(a["case_id"], [])
        v = vm.build(pack.loc[a["case_id"]].to_dict() if a["case_id"] in pack.index else {}, a, ev)
        chip_cls = STATUS_CHIP.get(c["status"], ("", ""))[0]
        head = vm.ACTION_TEXT.get(v.headline.get("action"), "—")
        sar = SAR_YES if a["sar"]["file"] else SAR_NO
        rows.append(f"<tr><td><a href='./?case={e(a['case_id'])}&view=saved' target='_self'>{e(a['case_id'])}</a></td>"
                    f"<td><span class='chip {chip_cls}'>{e(OUTCOME.get(c['verdict'], (c['verdict'],))[0])}</span></td>"
                    f"<td class='num'>{pct(v.p_final)}</td><td class='num'>{v.final.confidence * 100:.0f}%</td>"
                    f"<td>{e(c['pattern'].replace('_', ' '))}</td><td class='num'>{money(c['exposure_usd'])}</td>"
                    f"<td class='num'>{len(c['connected_card_ids'])}</td><td>{sar}</td>"
                    f"<td style='color:var(--ink)'>{e(head)}<div class='acts'>{e(v.headline.get('route', ''))}</div></td></tr>")
    st.html("<div class='tbl'><table><thead><tr><th>Case</th><th>Outcome</th><th style='text-align:right'>Fraud prob.</th>"
            "<th style='text-align:right'>Confidence</th><th>Pattern</th><th style='text-align:right'>Exposure</th>"
            "<th style='text-align:right'>Linked cards</th><th>SAR</th><th>Next best action</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def page_alerts():
    page_head("Investigations", "Alert queue", "Inbound alerts from the case pack, plus alerts the agent raised itself by monitoring the graph.")
    pack = case_pack()
    done = {p.stem for p in SETTINGS.cases_dir.glob("HHG-*.json")}
    rows = []
    for r in pack.itertuples():
        state = "<span class='chip c-legit'>investigated</span>" if r.case_id in done else "<span class='chip c-warn'>new</span>"
        rows.append(f"<tr><td><a href='./?case={e(r.case_id)}&view=saved' target='_self'>{e(r.case_id)}</a></td>"
                    f"<td class='mono' style='white-space:nowrap'>{e(r.opened_at)}</td><td>{e(r.trigger_type.replace('_', ' '))}</td>"
                    f"<td class='mono'>{e(r.flagged_txn_id)}</td><td>{e(vm.short(r.trigger_text, 120))}</td><td>{state}</td></tr>")
    t1, t2 = st.tabs([f"Inbound alerts · {len(pack)}", "Proactive · raised by the agent"])
    with t1:
        st.html("<div class='tbl'><table><thead><tr><th>Alert</th><th>Opened</th><th>Trigger</th><th>Txn</th><th>Alert text</th>"
                "<th>Status</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
    with t2:
        p = ROOT / "proactive" / "alerts.json"
        if not p.exists():
            st.html("<div class='empty'>Run <span class='mono'>python monitor.py</span> to scan the graph for rings and structuring.</div>")
            return
        al = json.loads(p.read_text())
        rings = sorted(al.get("device_rings", []), key=lambda r: -float(r.get("score", 0)))
        struct = al.get("structuring", [])
        st.html("<div class='kpis' style='grid-template-columns:repeat(3,1fr)'>"
                f"<div class='kpi'><div class='eyebrow'>Device rings</div><div class='n'>{len(rings)}</div><div class='l'>one device profile, many cards</div></div>"
                f"<div class='kpi'><div class='eyebrow'>Structuring bursts</div><div class='n'>{len(struct)}</div><div class='l'>just under $500, within an hour</div></div>"
                f"<div class='kpi'><div class='eyebrow'>Connected components</div><div class='n'>{len(al.get('wcc_components', []))}</div>"
                f"<div class='l'>WCC over client ↔ device</div></div></div>")
        pro = []
        for f in sorted((ROOT / "proactive" / "cases").glob("PRO-*.json")):
            a = json.loads(f.read_text())
            c = a["case"]
            chip_cls = STATUS_CHIP.get(c["status"], ("", ""))[0]
            pro.append(f"<tr><td class='mono'>{e(a['case_id'])}</td><td><span class='chip {chip_cls}'>{e(c['verdict'])}</span></td>"
                       f"<td class='num'>{pct(c['fraud_probability'])}</td><td>{e(c['pattern'].replace('_', ' '))}</td>"
                       f"<td class='num'>{money(c['exposure_usd'])}</td><td class='num'>{len(c['connected_card_ids'])}</td>"
                       f"<td>{e(vm.short(c['summary'], 140))}</td></tr>")
        if pro:
            st.html("<div class='eyebrow' style='margin:6px 0 8px'>Cases the agent opened on its own</div><div class='tbl'><table><thead><tr>"
                    "<th>Case</th><th>Outcome</th><th style='text-align:right'>Fraud prob.</th><th>Pattern</th>"
                    "<th style='text-align:right'>Exposure</th><th style='text-align:right'>Linked cards</th><th>Summary</th>"
                    "</tr></thead><tbody>" + "".join(pro) + "</tbody></table></div>")
        rr = "".join(f"<tr><td class='mono' style='font-size:12px'>{e(vm.short(r['device'], 60))}</td>"
                     f"<td class='num'>{len(r['cards'])}</td><td class='num'>{e(r['txns'])}</td>"
                     f"<td class='num'>{float(r['new_share']) * 100:.0f}%</td><td class='num'>{float(r['proxy_share']) * 100:.0f}%</td>"
                     f"<td class='num'>{float(r['score']):.1f}</td></tr>" for r in rings[:12])
        st.html("<div class='eyebrow' style='margin:18px 0 8px'>Top device rings</div><div class='tbl'><table><thead><tr><th>Device profile</th>"
                "<th style='text-align:right'>Cards</th><th style='text-align:right'>Txns</th><th style='text-align:right'>New device</th>"
                "<th style='text-align:right'>Proxy</th><th style='text-align:right'>Ring score</th></tr></thead><tbody>" + rr + "</tbody></table></div>")


def case_picker(key: str):
    ids = [p.stem for p in sorted(SETTINGS.cases_dir.glob("HHG-*.json"))]
    if not ids:
        st.html("<div class='empty'>No investigated cases yet.</div>")
        return None
    res = st.session_state.get("result")
    default = ids.index(res[1]["case_id"]) if res and res[1]["case_id"] in ids else 0
    cid = st.selectbox("Case", ids, index=default, key=key)
    a, ev = load_saved(cid)
    if not a:
        return None
    pack = case_pack().set_index("case_id")
    return (pack.loc[cid].to_dict() if cid in pack.index else {}), a, ev


def page_graph():
    page_head("Intelligence", "Investigation graph", "The TigerGraph neighbourhood the agent traversed for a case: "
              "transactions, cards, shared devices, connected cards, and the closed cases used as memory.")
    got = case_picker("g_case")
    if got:
        _, a, ev = got
        show_graph(a, ev, height=640)


def page_patterns():
    page_head("Intelligence", "Fraud patterns", "What the agent found across the benchmark, next to what the bank's closed cases record.")
    data = all_answers()
    cc = closed_cases()
    agent = Counter(a["case"]["pattern"] for a in data if a["case"]["verdict"] != "legitimate")
    fr = cc[cc.outcome == "confirmed_fraud"]
    mem_n = fr.groupby("pattern").case_id.count().to_dict()
    mem_x = fr.groupby("pattern").exposure_usd.mean().to_dict()
    pats = sorted(set(agent) | set(mem_n), key=lambda p: (-agent.get(p, 0), -mem_n.get(p, 0)))
    cards = []
    for p in pats:
        n_mem = int(mem_n.get(p, 0))
        undocumented = n_mem == 0
        avg = f" · avg {money(float(mem_x[p]))}" if n_mem else ""
        cards.append(f"<div class='kpi'><div class='eyebrow'>{'undocumented · new' if undocumented else 'documented pattern'}</div>"
                     f"<div style='font:700 17px var(--display);color:{'var(--pink)' if undocumented else 'var(--ink)'};margin-top:6px'>"
                     f"{e(p.replace('_', ' '))}</div>"
                     f"<div class='l' style='margin-top:8px'><b class='mono' style='color:var(--yellow)'>{agent.get(p, 0)}</b> agent case(s) · "
                     f"<b class='mono' style='color:var(--ink)'>{n_mem}</b> closed case(s){avg}</div></div>")
    st.html("<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px'>" + "".join(cards) + "</div>")
    doc = SETTINGS.knowledge_dir / "fraud_patterns.md"
    if doc.exists():
        with st.expander("Pattern playbook (knowledge base used by GraphRAG)"):
            st.markdown(doc.read_text(encoding="utf-8").replace("$", "\\$"))


def page_memory():
    page_head("Intelligence", "Case memory", "Search the bank's closed cases by meaning: TigerGraph native vector search over case embeddings.")
    q = st.text_input("Describe a situation", "new device online purchase, several cards share the same device profile, amounts nearly identical")
    k = st.slider("Results", 3, 15, 8)
    try:
        hits = backend().similar_closed_cases(embed(q), k)
    except Exception as ex:  # noqa: BLE001
        st.error(f"Vector search failed: {ex}")
        return
    st.html("<div class='evgrid'>" + "".join(memory_card(str(h.get("case_id") or h.get("id")), h, s) for h, s in hits) + "</div>")


def _inline(t: str) -> str:
    t = e(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<code class='pc'>\1</code>", t)
    return t


def md_html(text: str, drop_heading: bool = True) -> str:
    """Tiny markdown renderer for policy chunks: headings, paragraphs, bullet lists, pipe tables, bold, code."""
    lines = text.strip().splitlines()
    if drop_heading and lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]  # the section name is already shown in the card header
    out, para, table, items = [], [], [], []

    def flush():
        nonlocal para, table, items
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
        if items:
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
        if table:
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table
                    if not re.fullmatch(r"\|?[\s:|-]+\|?", r.strip())]
            if rows:
                head, body = rows[0], rows[1:]
                out.append("<table class='pt'><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head)
                           + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r)
                                                              + "</tr>" for r in body) + "</tbody></table>")
        para, table, items = [], [], []

    for ln in lines:
        t = ln.strip()
        if not t:
            flush()
        elif t.startswith("|"):
            if para or items:
                flush()
            table.append(t)
        elif t.startswith("#"):
            flush()
            out.append(f"<div class='ph'>{_inline(t.lstrip('#').strip())}</div>")
        elif re.match(r"^[-*] ", t):
            if para or table:
                flush()
            items.append(t[2:])
        else:
            if table or items:
                flush()
            para.append(t)
    flush()
    return "<div class='md'>" + "".join(out) + "</div>"


def page_policies():
    page_head("Intelligence", "Policies", "Fraud Policy v1.0 is code (agent/policy.py). GraphRAG retrieves the clause the agent cites.")
    q = st.text_input("Ask the policy", "when may the agent block a card without approval?")
    try:
        hits = backend().policy_search(embed(q), 5)
    except Exception as ex:  # noqa: BLE001
        st.error(f"GraphRAG search failed: {ex}")
        hits = []
    out = []
    for h, s in hits:
        out.append(f"<div class='ev neutral'><div class='m' style='margin:0 0 6px'><span class='badge rag'>GRAPHRAG</span>"
                   f"<span class='ref'>{e(h.get('doc'))} · {e(h.get('section'))}</span><span class='lr'>relevance {s:.2f}</span></div>"
                   f"{md_html(str(h.get('text', '')))}</div>")
    st.html("<div class='evgrid'>" + "".join(out) + "</div>")
    st.html("<div class='eyebrow' style='margin:22px 0 8px'>Approval routes</div><div class='gov' style='grid-template-columns:repeat(3,1fr)'>"
            "<div><div class='eyebrow'>auto · agent executes</div><div class='v'>Allow, monitor, warn, verify, step-up, create case, "
            "escalate, close no fraud</div></div>"
            "<div><div class='eyebrow'>L1 · team lead</div><div class='v'>Decline transaction; block card up to $2,500 exposure</div></div>"
            "<div><div class='eyebrow'>L2 · fraud manager</div><div class='v'>Block card above $2,500; block all cards; file SAR</div></div></div>")
    doc = SETTINGS.knowledge_dir / "fraud_policy.md"
    if doc.exists():
        with st.expander("Full policy text"):
            st.markdown(doc.read_text(encoding="utf-8").replace("$", "\\$"))


def page_activity():
    page_head("System", "Agent activity", "Every graph call the agent made, how it was made, and how long it took.")
    traces = all_traces()
    calls = []
    for cid, evs in traces.items():
        for ev in evs:
            if ev["kind"] == "tool" and isinstance(ev.get("detail"), dict):
                calls.append({"case": cid, "query": ev["title"].split("(")[0], "transport": str(ev["detail"].get("transport", "")),
                              "latency": float(ev["detail"].get("latency_s", 0) or 0)})
    if not calls:
        st.html("<div class='empty'>No traces yet.</div>")
        return
    df = pd.DataFrame(calls)
    mcp = (df.transport == "mcp").mean()
    llm = sum(1 for evs in traces.values() for ev in evs if ev["kind"] == "llm")
    st.html("<div class='kpis' style='grid-template-columns:repeat(4,1fr)'>"
            f"<div class='kpi'><div class='eyebrow'>Graph calls</div><div class='n'>{len(df)}</div><div class='l'>{len(traces)} cases</div></div>"
            f"<div class='kpi'><div class='eyebrow'>Via TigerGraph MCP</div><div class='n'>{mcp * 100:.0f}%</div><div class='l'>run_installed_query</div></div>"
            f"<div class='kpi'><div class='eyebrow'>Median latency</div><div class='n'>{df.latency.median():.2f}s</div><div class='l'>per graph call</div></div>"
            f"<div class='kpi'><div class='eyebrow'>LLM steps</div><div class='n'>{llm}</div><div class='l'>bounded investigator + writer</div></div></div>")
    g = df.groupby("query").agg(calls=("case", "count"), cases=("case", "nunique"), p50=("latency", "median"),
                                maxl=("latency", "max")).sort_values("calls", ascending=False)
    m = g.calls.max()
    rows = "".join(f"<tr><td class='mono' style='color:var(--ink)'>{e(q)}</td><td style='width:38%'><div style='height:8px;border-radius:4px;"
                   f"background:var(--green);width:{r.calls / m * 100:.0f}%'></div></td><td class='num'>{int(r.calls)}</td>"
                   f"<td class='num'>{int(r.cases)}</td><td class='num'>{r.p50:.2f}s</td><td class='num'>{r.maxl:.2f}s</td></tr>"
                   for q, r in g.iterrows())
    st.html("<div class='tbl'><table><thead><tr><th>Installed query</th><th></th><th style='text-align:right'>Calls</th>"
            "<th style='text-align:right'>Cases</th><th style='text-align:right'>p50</th><th style='text-align:right'>Max</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table></div>")


def page_audit():
    page_head("System", "Audit log", "What the agent executed on its own, what it queued for a human, and what humans decided.")
    traces = all_traces()
    rows = []
    for ap in reversed(st.session_state.get("approvals", [])):
        rows.append(("this session", ap["case"], "approval", ap["title"], "human"))
    for cid, evs in traces.items():
        for ev in evs:
            d = ev.get("detail") or {}
            if ev["kind"] == "execute" and isinstance(d, dict):
                for x in d.get("executed", []):
                    rows.append((ev["ts"], cid, "executed", x, "agent · auto"))
                for x in d.get("awaiting", []):
                    rows.append((ev["ts"], cid, "queued", x, "awaiting human"))
            elif ev["kind"] in ("memory", "guardrail", "approval"):
                rows.append((ev["ts"], cid, ev["kind"], vm.short(ev["title"], 120), "agent"))
    kind_chip = {"executed": "c-legit", "queued": "c-warn", "approval": "c-legit", "guardrail": "c-crit", "memory": ""}
    body = "".join(f"<tr><td class='mono' style='white-space:nowrap'>{e(t)}</td>"
                   f"<td><a href='./?case={e(c)}&view=saved' target='_self'>{e(c)}</a></td>"
                   f"<td><span class='chip {kind_chip.get(k, '')}'>{e(k)}</span></td><td style='color:var(--ink)'>{e(x)}</td>"
                   f"<td class='muted'>{e(who)}</td></tr>" for t, c, k, x, who in rows)
    st.html(f"<div class='muted' style='font-size:13px;margin-bottom:10px'>{len(rows)} entries · every case's events are also stored "
            "in TigerGraph as <span class='mono'>CaseEvent</span> vertices linked to its <span class='mono'>FraudCase</span>.</div>"
            "<div class='tbl'><table><thead><tr><th>Time</th><th>Case</th><th>Type</th><th>Action / event</th><th>By</th></tr></thead>"
            "<tbody>" + body + "</tbody></table></div>")


def page_agent():
    page_head("Investigations", "Ask the agent",
              "A Gemini agent built with Google's Agent Development Kit. It picks the TigerGraph tools, investigates and "
              "explains. Verdicts, probabilities and actions still come from the policy engine, and a guardrail removes "
              "claims the graph evidence does not support.")
    try:
        from sentinel_adk import agent as adk_agent
        from sentinel_adk.chat import Chat
    except Exception as ex:  # noqa: BLE001
        st.error(f"ADK agent unavailable: {ex}. Install it with `pip install google-adk`.")
        return
    adk_agent.use_backend(backend())
    if "adk_chat" not in st.session_state:
        st.session_state["adk_chat"] = Chat()
        st.session_state["adk_log"] = []
    log = st.session_state["adk_log"]
    c1, c2 = st.columns([5, 1], vertical_alignment="center")
    c1.caption(f"Model: {adk_agent.MODEL} · "
               + ("Vertex AI" if str(__import__('os').getenv("GOOGLE_GENAI_USE_VERTEXAI", "")).lower() in ("true", "1")
                  else "Gemini API") + " · tools: " + ", ".join(t.__name__ for t in adk_agent.root_agent.tools))
    if c2.button("New chat", use_container_width=True):
        st.session_state.pop("adk_chat")
        st.rerun()
    if not log:
        st.html("<div class='sub' style='margin:6px 0 14px'>Try: <b>Investigate HHG-003</b> · "
                "<b>How are the cards in HHG-006 linked?</b> · <b>Why does blocking need a team lead?</b> · "
                "<b>Investigate transaction 3475414, the customer says it was not them</b></div>")
    for m in log:
        with st.chat_message(m["role"]):
            if m.get("steps"):
                with st.expander(f"{sum(1 for x in m['steps'] if x['kind'] == 'call')} tool call(s)"):
                    for x in m["steps"]:
                        if x["kind"] == "call":
                            st.code(f"{x['name']}({json.dumps(x['args'])})", language="python")
            st.markdown(m["text"].replace("$", "\\$"))
    q = st.chat_input("Ask about an alert, a case or the policy")
    if q:
        log.append({"role": "user", "text": q})
        with st.chat_message("user"):
            st.markdown(q.replace("$", "\\$"))
        with st.chat_message("assistant"):
            with st.spinner("Agent working on TigerGraph ..."):
                try:
                    a, steps = st.session_state["adk_chat"].ask(q)
                except Exception as ex:  # noqa: BLE001
                    a, steps = f"The agent hit an error: {ex}", []
        log.append({"role": "assistant", "text": a or "(no answer)", "steps": steps})
        st.rerun()


# =========================================================================== navigation
pages = {
    "Investigations": [st.Page(page_investigate, title="Investigate", icon=":material/policy:", url_path="investigate", default=True),
                       st.Page(page_agent, title="Ask the agent", icon=":material/smart_toy:", url_path="agent"),
                       st.Page(page_portfolio, title="Case Portfolio", icon=":material/folder_open:", url_path="portfolio"),
                       st.Page(page_alerts, title="Alert Queue", icon=":material/notifications_active:", url_path="alerts")],
    "Intelligence": [st.Page(page_graph, title="Investigation Graph", icon=":material/hub:", url_path="graph"),
                     st.Page(page_patterns, title="Fraud Patterns", icon=":material/pattern:", url_path="patterns"),
                     st.Page(page_memory, title="Case Memory", icon=":material/psychology:", url_path="memory"),
                     st.Page(page_policies, title="Policies", icon=":material/gavel:", url_path="policies")],
    "System": [st.Page(page_activity, title="Agent Activity", icon=":material/timeline:", url_path="activity"),
               st.Page(page_audit, title="Audit Log", icon=":material/fact_check:", url_path="audit")],
}
nav = st.navigation(pages)

with st.sidebar:
    s = status_info()
    if s["ok"]:
        tg = ("Connected" if s["name"] == "tigergraph" else "Local mode") + f" · {s['via']}"
        llm_p = LLM(SETTINGS)
        llm_on = llm_p.provider != "none"
        st.html("<div class='side-status'>"
                f"<div><span class='d' style='background:var(--legit)'></span>TigerGraph<b>{e(tg)}</b></div>"
                "<div><span class='d' style='background:var(--legit)'></span>Agent<b>Online</b></div>"
                "<div><span class='d' style='background:var(--legit)'></span>Policy engine<b>v1.0 active</b></div>"
                f"<div><span class='d' style='background:{'var(--legit)' if llm_on else 'var(--mute)'}'></span>"
                f"LLM<b>{e(llm_p.provider if llm_on else 'off')}</b></div>"
                f"<div style='margin-top:6px'>Transactions<b>{int(s.get('txns', 0)):,}</b></div>"
                f"<div>Closed cases<b>{int(s.get('closed_cases', 0)):,}</b></div>"
                f"<div>Agent cases<b>{int(s.get('agent_cases', 0)):,}</b></div>"
                "<div style='margin-top:14px;font:700 14px var(--display);color:var(--yellow)'>Less Dashboard. More Investigation.</div>"
                "<div class='muted' style='font-size:11.5px'>TigerGraph × Hacker House Goa 2026</div></div>")
    else:
        status_info.clear()
        st.html("<div class='side-status'><div><span class='d' style='background:var(--pink)'></span>TigerGraph"
                "<b>unreachable</b></div><div class='muted' style='font-size:11.5px;line-height:1.5;margin-top:4px'>"
                "Savanna workspace may be suspended. Resume it in the Savanna console, then reload. Saved cases "
                "still open.</div></div>")

nav.run()
