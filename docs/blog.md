# The agent that knows when to stop

*Task #4 · TigerGraph problem statement · Hacker House Goa 2026 · built on TigerGraph Savanna*

A risk score pings. Is it fraud, a holiday, or a new phone? We built an AI agent that works the alert like a sharp analyst: it digs through the graph, admits what it doesn't know, asks for the one piece of evidence that would settle it, and recommends the next move with the right person signing off.

**590,742** transactions in the graph · **5,565** closed cases as memory · **16** GSQL queries via MCP · **0.914** memory-model AUC (bank score: 0.866) · **28** cards in the biggest ring

## Alerts are cheap. Decisions are not.

Fraud teams are never short of alerts. What they're short of is time to turn each one into a call they can defend. For every ping an analyst pulls the card history, checks the device, hunts for other victims, rereads the policy, decides whether to phone the customer, and writes it all up. Usually after the money has moved.

So for Task #4 we built **SentinelGraph**: an agent that runs that loop end to end on TigerGraph and hands back a decision with receipts.

## Three things the data told us first

The dataset is the IEEE-CIS card data, 590,742 transactions over six months, with the fraud label taken away. In its place: a bank risk score, 5,565 closed investigations from July to October, a fraud policy, and 20 benchmark alerts from November and December.

- **A "customer" isn't a person.** Customer IDs come from an issuer code, so one card can hold 2,788 transactions across dozens of billing regions. Card-level checks are noise. We added a `Client` vertex, a latent cardholder built from card + billing region + account-open day. In the closed cases, 85% of a fraud client's transactions are fraud.
- **The bank's memory is lopsided, and that's useful.** All 4,665 confirmed frauds began with a cardholder report. All 900 cleared cases began with a model score the cardholder then explained: travel (716), a new phone (158), a purchase they meant (26). A score alone is weak evidence. A denial is strong evidence.
- **Card IDs come back exactly.** Ranking each customer's `card6` values reproduces every card ID in the closed cases and the case pack.

> A risk score is a reason to look. Never a verdict.

## One alert, six moves

Every layer has one job. Graph queries find facts. A deterministic evidence layer weighs them. A policy engine picks the actions. The LLM probes open questions and writes the story, and it never sets a probability or an action.

1. **Open the case.** A trigger arrives (score, customer report or analyst). A case opens with an audit trail.
2. **Dig the graph.** 16 installed GSQL queries through the TigerGraph MCP server, about a tenth of a second each.
3. **Remember.** GraphRAG vector search over closed cases, earlier agent cases and policy clauses.
4. **Weigh it.** Each finding gets a likelihood ratio and a family. Families combine in log-odds; correlated signals can't pile up.
5. **Stop or ask.** Two independent families agree past 85% or 15%? Stop. Otherwise ask for the one piece of evidence that settles it.
6. **Act and write back.** Auto actions run. L1 and L2 actions wait for a human. The case goes back into the graph as memory.

### One graph, three layers

- **Evidence.** Customer, Card, Client and Txn, linked to DeviceProfile, EmailDomain and BillingRegion, with a `NEXT_TXN` chain per card.
- **Case memory.** 5,565 `ClosedCase` vertices tied to their transactions, cards and pattern, plus every `FraudCase` the agent opens and its `CaseEvent` trail.
- **Knowledge.** `PolicyChunk` vertices, one per policy rule, plus typologies, a FinCEN/FATF/FFIEC digest and lessons mined from closed cases.

All three carry TigerGraph's native 256-dimension vector attribute, so memory lookups are a `vectorSearch()` inside an installed query, right next to the graph hops.

### Queries that do the heavy lifting

- `peer_txns` goes two hops: flagged transaction → its device or email → purchases on *other* cards at a similar amount within 48 hours. This is the "what happened on other cards?" question.
- `ring_components` runs weakly connected components over the client↔device graph and isolates rings as single components.
- `device_ring_scan` and `amount_band_scan` sweep the whole exam period, so the agent can raise alerts nobody reported.
- `prior_cases` and `device_cases` pull memory by adjacency: which closed cases touched this device?

The agent talks to TigerGraph through the official `tigergraph-mcp` server (`tigergraph__run_installed_query` for every read, vector search included), with RESTPP as a fallback. Every call in the trace records which transport served it.

### The agentic bits

**A prior learned from memory.** The closed cases cover about 3.4% of July to October transactions, close to the true fraud rate, so we trained a gradient-boosted model on them. On an October hold-out it scores AUC 0.914 against 0.866 for the bank's score, with nearly double the average precision.

**Knowing when to stop.** Policy section 6, as code. If the case isn't settled, the agent picks the evidence that would settle it: step-up authentication for an online score alert, customer verification for a dispute, R7 verification when a disputed charge matches the customer's own recurring pattern. Replies aren't provided this round, so the agent assumes the reply the evidence supports, writes the assumption down, then re-assesses.

**Policy as code.** R1 to R10, case versus report, routing by exposure, and a guard that refuses breaches like blocking on one weak signal or blocking all cards without two compromised ones.

> Same evidence, same decision. We re-ran all 20 alerts and every one came back identical.

## What the graph caught

- **HHG-006 · Threshold structuring.** Four online purchases in 30 minutes, each just under $500, $1,906.07 in total. The same trick shows up on 11 other cards and matches five undocumented September cases. SAR filed, escalated under R9.
- **HHG-014 · A 28-card device ring.** One Samsung profile behind an anonymous proxy, marked New on every account, used across 28 cards. WCC isolates it as one component. The August closed cases were the same device, so memory changes the label.
- **HHG-019, HHG-011, HHG-016 · Rings you can't see from one card.** Each purchase looks ordinary on its own card. On the graph, the same rare device made near-identical purchases on 3 to 5 other cards within days. R6: report and watch the connected cards.
- **HHG-018 · Disputed, but it recurs.** A customer disputes $39.08. The graph shows the same amount, region and product recurring since August. R7: open a case, verify, send a reminder. No block.
- **HHG-003 · Honest about doubt.** A denied $49 purchase in a region the card uses all the time. The card gets blocked (R2), but the outcome stays uncertain and goes to an analyst (R8) instead of faking confidence.
- **Half were false alarms.** Weekly local purchases, travel, new phones. The agent verifies the ones it must and closes the rest with a written reason.

## Scoreboard

10 legitimate, 9 fraud, 1 uncertain. Six SARs drafted for L2 sign-off. Every case is written back into TigerGraph as a `FraudCase` with its audit trail. The full table and answer files are in the repo (`cases/`).

## What we learned

**Is schema design really the magic?** Yes. The Client vertex and the device fan-out query did more for accuracy than any model tuning.

**Where does the LLM belong?** Where language is the product. When it computed probabilities, runs weren't repeatable. As a bounded prober and a checked writer, it helps without drifting. Its text is rejected if it cites an ID that isn't in the evidence.

**Is "uncertain" a cop-out?** No. It's the honest answer when evidence disagrees, and the policy knows what to do with it: protect the customer now, let a human decide.

**What's next?** Real reply channels (SMS, app push) instead of assumed replies. Streaming ingestion with the ring scans running nonstop. Likelihood ratios learned from resolved agent cases. Louvain communities to catch rings that share more than one element.

---

*Stack: TigerGraph Savanna · GSQL · TigerGraph MCP · native vector search · Python · Gemini · Streamlit.*

#TigerGraph #GraphRAG #HHGoa #HackerHouseGoa
