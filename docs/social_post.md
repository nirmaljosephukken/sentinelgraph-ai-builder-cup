# Social posts

## LinkedIn

For the @247pmstudio Hacker House Goa 2026 TigerGraph challenge, I built SentinelGraph: an AI agent that investigates card fraud end to end on @TigerGraphDB.

The bank's risk score is a reason to look, never a verdict. In this bank's own history, all 900 alerts raised by the score alone turned out to be false alarms. So the agent works like a careful analyst:

🔎 Gathers evidence through the TigerGraph MCP server: 16 GSQL queries, including two-hop "what happened on other cards" lookups and WCC ring detection
🧠 Recalls similar past investigations with GraphRAG (vector search over 5,565 closed cases and the fraud policy)
⚖️ Makes its uncertainty explicit, stops when two independent lines of evidence agree, and otherwise asks for the one piece of evidence that would settle the case
🧭 Recommends the next best action with its approval route (auto / L1 / L2) under the bank's policy, and writes a SAR when one is required
💾 Writes every case back into the graph, so the next investigation can find it

Things the graph caught that the card-level view missed:
• a 28-card device ring behind an anonymous proxy
• "threshold structuring": four purchases just under $500 in 30 minutes, repeated on 12 cards
• three small rings where one rare device made similar purchases on 3–5 cards in a few days

Blog: https://dev.to/nekku/the-agent-that-knows-when-to-stop-agentic-fraud-investigation-on-tigergraph-5d18 · Demo: https://youtu.be/Rw8Wb1xVlPg · Code: https://github.com/nirmaljosephukken/HH_GOA_Task_4

#TigerGraph #GraphRAG #AIagents #FraudDetection #MCP

## X (280 chars)

Built an AI fraud-investigation agent on @TigerGraphDB for @247pmstudio #HackerHouseGoa: GSQL + MCP, GraphRAG over 5.6k closed cases, explicit uncertainty, policy-routed next best actions. It found a 28-card device ring and a sub-$500 structuring scheme. https://youtu.be/Rw8Wb1xVlPg
