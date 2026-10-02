---
title: "The Agent That Knows When to Stop: Agentic Fraud Investigation on TigerGraph"
published: false
description: "SentinelGraph, our Hacker House Goa 2026 Task 4 build: an AI agent that investigates card fraud on TigerGraph with GSQL, MCP and GraphRAG, admits what it doesn't know, and recommends a defensible next best action."
tags: tigergraph, ai, graphrag, python
cover_image:
---

*Task #4 · TigerGraph problem statement · Hacker House Goa 2026*

A risk score pings. Is it fraud, a holiday, or a new phone?

We built **SentinelGraph**, an AI agent that works the alert like a sharp analyst: it digs through the graph, admits what it doesn't know, asks for the one piece of evidence that would settle it, and recommends the next move with the right person signing off.

**590,742** transactions in the graph · **5,565** closed cases as memory · **16** GSQL queries via MCP · **0.914** memory-model AUC (bank score: 0.866) · **28** cards in the biggest ring we found

🔗 **Code:** https://github.com/nirmaljosephukken/HH_GOA_Task_4 · 🎬 **Demo:** https://youtu.be/Rw8Wb1xVlPg

---

## 1. What we built

Fraud teams are never short of alerts. They're short of time to turn each one into a call they can defend. For every ping an analyst pulls the card history, checks the device, hunts for other victims, rereads the policy, decides whether to phone the customer, and writes it all up. Usually after the money has moved.

SentinelGraph runs that loop end to end:

- **Triggers:** a bank risk score, a customer report, or an analyst request.
- **Investigates** the card, the latent cardholder, devices, emails, regions and *other cards* through TigerGraph.
- **Remembers** 5,565 closed investigations and every case it opened before.
- **Measures its own uncertainty** and stops only when two independent lines of evidence agree.
- **Asks for more evidence** through policy-approved actions (customer validation, step-up authentication, analyst review) when it isn't sure.
- **Recommends the next best action** with its approval route (auto / L1 team lead / L2 fraud manager), drafts a SAR when policy requires one, and writes the whole case back into the graph.
- **SentinelGraph console** (Streamlit) shows the alert, the live investigation, what it found, how certain it is, what happens next, the evidence graph, and why it stopped.

We ran it on the 20 benchmark alerts: **10 legitimate, 9 fraud, 1 uncertain, 6 SARs**. Re-running all 20 gives the same decisions every time.

### Reading the room first

The dataset is the IEEE-CIS card data with the fraud label taken away. In its place: a bank risk score, 5,565 closed investigations (July to October), a fraud policy, five documented patterns, and 20 alerts from November and December. Three findings shaped everything:

- **A "customer" isn't a person.** Customer IDs come from an issuer code, so one card can hold 2,788 transactions across dozens of billing regions. We added a `Client` vertex: a latent cardholder built from card + billing region + account-open day. In closed cases, 85% of a fraud client's transactions are fraud.
- **The bank's memory is lopsided, and that's useful.** All 4,665 confirmed frauds began with a cardholder report. All 900 cleared cases began with a model score the cardholder explained (travel 716, new phone 158, intended purchase 26). *A risk score is a reason to look. Never a verdict.*
- **Card IDs come back exactly.** Ranking each customer's `card6` values reproduces every card ID in the closed cases and the case pack.

## 2. The architecture

Every layer has one job. Graph queries find facts. A deterministic evidence layer weighs them. A policy engine picks the actions. The LLM probes open questions and writes the story, and it never sets a probability or an action.

```
Trigger (score / customer / analyst)
   │
   ▼
Case orchestrator ── state machine + audit trail ──────────────┐
   │  MCP: tigergraph__run_installed_query   GraphRAG: vectorSearch
   ▼                                                            │
TigerGraph Savanna (FraudGraph)                                 │
   │                                                            │
   ▼                                                            │
Evidence layer ── detectors → likelihood ratios by family       │
   ▼                                                            │
Uncertainty engine ── log-odds fusion, confidence, open questions
   ▼                                                            │
Policy engine ── R1–R10, case vs report, stop rule, routes, guardrails
   │                       │                                    │
   ▼                       ▼                                    │
ask for evidence     next best action (auto runs, L1/L2 wait)   │
(verify / step-up)         │                                    │
   └──► re-assess          ▼                                    │
                     FraudCase + CaseEvents written back ◄──────┘

LLM (Gemini): bounded extra tool calls + narrative/SAR writer, output validated
```

One alert, six moves:

1. **Open the case** with an audit trail.
2. **Dig the graph:** 16 installed GSQL queries through the TigerGraph MCP server, about 0.1 s each.
3. **Remember:** GraphRAG vector search over closed cases, earlier agent cases and policy clauses.
4. **Weigh it:** each finding gets a likelihood ratio and an evidence family (ml, trigger, sequence, network, device, behaviour, history, customer). Within a family only the strongest counts, so correlated signals can't pile up. Families multiply in log-odds.
5. **Stop or ask:** two independent families agree past 85% or 15%? Stop. Otherwise request the evidence that would settle it.
6. **Act and write back:** auto actions execute, L1/L2 actions wait for a human, the case goes back into the graph as memory.

## 3. How TigerGraph is used

**One graph, three layers:**

- **Evidence graph:** `Customer–Card–Client–Txn`, with `Txn` linked to `DeviceProfile`, `EmailDomain` (purchaser and recipient) and `BillingRegion`, plus a `NEXT_TXN` chain per card.
- **Case memory:** 5,565 `ClosedCase` vertices linked to their transactions, cards, connected cards and pattern. Every `FraudCase` the agent opens is stored too, with edges to the transactions, cards, devices and closed cases it used, and a `CaseEvent` chain as its audit trail.
- **Knowledge:** `PolicyChunk` vertices, one per policy rule, plus fraud typologies, a FinCEN/FATF/FFIEC digest and lessons mined from closed cases.

`ClosedCase`, `FraudCase` and `PolicyChunk` carry TigerGraph's **native 256-dimension vector attribute**, so memory lookups are a `vectorSearch()` inside an installed query, right next to the graph hops.

**Sixteen installed GSQL queries**, each exposed to the agent as a tool. Highlights:

- `peer_txns`: two hops, flagged transaction → its device or email → purchases on *other* cards at a similar amount within 48 hours. This is the "what happened on other cards?" question.
- `card_profile`: a behavioural baseline in one pass with `MapAccum`s over products, regions, devices and emails.
- `ring_components`: **weakly connected components** (min-label propagation adapted from `tg_wcc`) over the client↔device co-usage graph. It isolates the 28-card ring as one component.
- `device_ring_scan` and `amount_band_scan`: sweep the whole exam period, so the agent raises alerts nobody reported (`monitor.py`).
- `prior_cases` and `device_cases`: memory by adjacency. Which closed cases touched this device?

**TigerGraph MCP.** The agent launches the official [`tigergraph-mcp`](https://github.com/tigergraph/tigergraph-mcp) server over stdio, discovers its tools, and calls `tigergraph__run_installed_query` for every read, vector searches included. Argument names come from the tool schema at runtime. If MCP is unavailable it falls back to RESTPP, and every call in the trace records which transport served it.

**Loading.** Streamed parallel RESTPP upserts loaded 590k transactions and about 3M edges into Savanna in under two minutes.

## 4. The agentic capabilities

**Explicit uncertainty.** Every detector returns a claim, the query it came from, the entity IDs it rests on, a likelihood ratio and a family. The case records the prior, the posterior, each family's contribution, which families argue each way, and the open questions ("device ownership not established", "evidence conflicts").

**A calibrated prior learned from case memory.** The closed cases cover about 3.4% of July to October transactions, close to the true fraud rate, so we trained a gradient-boosted model on them. Trained on July to September and tested on October: **AUC 0.914 vs 0.866 for the bank's score, with nearly double the average precision.**

**Knowing when to stop.** Policy section 6, as code: stop at ≥ 0.85 or ≤ 0.15 with two independent families agreeing. Otherwise the agent picks the evidence request that best resolves the case: step-up authentication for an online score alert, customer verification for a dispute, R7 verification for a disputed charge that matches the customer's own recurring pattern. Replies aren't provided in this round, so a simulator assumes the reply the evidence supports, records the assumption and its basis, and the agent re-assesses. The next best action is recorded **before** and **after** the evidence, with what changed.

**Policy as code, with permissions.** R1–R10, the case-vs-report rule, exposure-based routing, action ordering, and a guard that refuses breaches (blocking on a single weak signal, `BLOCK_ALL_CARDS` without two compromised cards, blocking a recurring dispute). Only `auto` actions execute. L1 and L2 actions wait in the console's approval queue, and every approval is written to the case's audit trail in TigerGraph.

**Memory that changes the answer.**

- **HHG-014:** `device_cases` returns closed cases analysts labelled *undocumented*, so the agent labels the new ring undocumented too and escalates under R9.
- **HHG-006:** vector retrieval surfaces five undocumented September structuring cases.
- **Legitimate alerts:** cleared cases on the same card ("confirmed travel") are cited as precedent.

**The LLM where language is the product.** Gemini gets a bounded budget of extra tool calls to probe open questions, then writes the summary, pattern description and SAR narrative. Any text that cites an ID not present in the evidence is rejected. Its notes carry zero weight in the probability, which is why decisions are reproducible.

### What the graph caught

- **HHG-006 · Threshold structuring.** Four online purchases in 30 minutes, each just under $500 ($1,906.07 total). Same trick on 11 other cards; matches five undocumented September cases. SAR, R9 escalation.
- **HHG-014 · A 28-card device ring.** One Samsung profile behind an anonymous proxy, marked *New* on every account. The November wave of the August ring.
- **HHG-019, HHG-011, HHG-016 · Rings you can't see from one card.** Each purchase looks ordinary on its own card. On the graph, the same rare device made near-identical purchases on 3–5 other cards within days. R6: report and monitor connected cards.
- **HHG-018 · Disputed, but it recurs.** A $39.08 charge recurring at the same amount, region and product since August. R7: verify and remind, no block.
- **HHG-003 · Honest about doubt.** A denied $49 purchase in a region the card uses all the time. The card is blocked (R2), but the outcome stays *uncertain* and goes to an analyst (R8).

### Scoreboard: all 20 alerts

| Case | Outcome | P(fraud) | Pattern | Exposure | Linked cards | SAR | Evidence asked | Final next best action |
|---|---|---|---|---|---|---|---|---|
| HHG-001 | legitimate | 0.01 | none | $0.00 | 0 | no | none | `ALLOW_TRANSACTION` → `GENERATE_REPORT` → `CLOSE_NO_FRAUD` |
| HHG-002 | legitimate | 0.01 | none | $0.00 | 0 | no | step up auth | `ALLOW_TRANSACTION` → `CREATE_CASE` → `CLOSE_NO_FRAUD` |
| HHG-003 | uncertain | 0.63 | out of region use | $49.00 | 0 | no | customer validation | `BLOCK_CARD` → `CREATE_CASE` → `ESCALATE_TO_ANALYST` |
| HHG-004 | fraud | 0.73 | card not present new device | $128.33 | 0 | no | customer validation | `BLOCK_CARD` → `CREATE_CASE` |
| HHG-005 | legitimate | 0.01 | none | $0.00 | 0 | no | step up auth | `ALLOW_TRANSACTION` → `CREATE_CASE` → `CLOSE_NO_FRAUD` |
| HHG-006 | fraud | 0.99 | undocumented | $1,906.07 | 11 | yes | none | `BLOCK_CARD` → `CREATE_CASE` → `FILE_REPORT` → `MONITOR_CONNECTED_CARDS` → `ESCALATE_TO_ANALYST` |
| HHG-007 | legitimate | 0.01 | none | $0.00 | 0 | no | none | `ALLOW_TRANSACTION` → `GENERATE_REPORT` → `CLOSE_NO_FRAUD` |
| HHG-008 | fraud | 0.99 | card not present fraud | $166.97 | 1 | yes | none | `BLOCK_CARD` → `CREATE_CASE` → `FILE_REPORT` → `MONITOR_CONNECTED_CARDS` |
| HHG-009 | fraud | 0.98 | card not present fraud | $30.02 | 0 | no | none | `BLOCK_CARD` → `CREATE_CASE` |
| HHG-010 | legitimate | 0.01 | none | $0.00 | 0 | no | step up auth | `ALLOW_TRANSACTION` → `CREATE_CASE` → `CLOSE_NO_FRAUD` |
| HHG-011 | fraud | 0.95 | card not present new device | $131.30 | 5 | yes | none | `BLOCK_CARD` → `CREATE_CASE` → `FILE_REPORT` → `MONITOR_CONNECTED_CARDS` |
| HHG-012 | legitimate | 0.01 | none | $0.00 | 0 | no | none | `ALLOW_TRANSACTION` → `GENERATE_REPORT` → `CLOSE_NO_FRAUD` |
| HHG-013 | legitimate | 0.01 | none | $0.00 | 0 | no | step up auth | `ALLOW_TRANSACTION` → `CREATE_CASE` → `CLOSE_NO_FRAUD` |
| HHG-014 | fraud | 0.89 | undocumented | $439.61 | 27 | yes | none | `BLOCK_CARD` → `CREATE_CASE` → `FILE_REPORT` → `MONITOR_CONNECTED_CARDS` → `ESCALATE_TO_ANALYST` |
| HHG-015 | legitimate | 0.01 | none | $0.00 | 0 | no | step up auth | `ALLOW_TRANSACTION` → `CREATE_CASE` → `CLOSE_NO_FRAUD` |
| HHG-016 | fraud | 0.99 | card not present new device | $59.67 | 3 | yes | none | `BLOCK_CARD` → `CREATE_CASE` → `FILE_REPORT` → `MONITOR_CONNECTED_CARDS` |
| HHG-017 | legitimate | 0.03 | none | $0.00 | 0 | no | none | `ALLOW_TRANSACTION` → `GENERATE_REPORT` → `CLOSE_NO_FRAUD` |
| HHG-018 | legitimate | 0.02 | none | $0.00 | 0 | no | customer validation | `CREATE_CASE` → `WARN_CUSTOMER` → `CLOSE_NO_FRAUD` |
| HHG-019 | fraud | 0.99 | card not present new device | $99.92 | 4 | yes | none | `BLOCK_CARD` → `CREATE_CASE` → `FILE_REPORT` → `MONITOR_CONNECTED_CARDS` |
| HHG-020 | legitimate | 0.01 | none | $0.00 | 0 | no | step up auth | `ALLOW_TRANSACTION` → `CREATE_CASE` → `CLOSE_NO_FRAUD` |

## 5. What we learned

- **Schema design is investigation design.** The `Client` vertex and the device fan-out query did more for accuracy than any model tuning.
- **Put the LLM where language is the product.** When it computed probabilities, runs weren't repeatable. As a bounded prober and a validated writer, it helps without drifting.
- **"Uncertain" is an honest answer.** When evidence disagrees, protect the customer now and let a human decide.
- **Graph memory beats flat memory.** Retrieving past cases by *adjacency* (same device, same card) and by *similarity* (vectors) together caught things neither did alone.

## 6. What we'd improve with more time

- Real reply channels (SMS, app push) instead of simulated replies, feeding outcomes back as training signal.
- Streaming ingestion into TigerGraph with the ring and structuring scans running continuously.
- Likelihood ratios learned from resolved agent cases instead of set by hand.
- Louvain community detection over client↔device↔email to catch rings that share more than one element.
- External enrichment (BIN/issuer, IP reputation) as additional evidence families.

---

**Stack:** TigerGraph Savanna · GSQL · TigerGraph MCP · native vector search · Python · Gemini · Streamlit

Built for Hacker House Goa 2026 with @TigerGraphDB. Code, the 20 answer files and full investigation traces: https://github.com/nirmaljosephukken/HH_GOA_Task_4
