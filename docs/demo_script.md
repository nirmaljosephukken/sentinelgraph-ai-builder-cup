# Demo video script (target 3:50, hard limit 5:00)

Built around the judging criteria: next best action under uncertainty (25%), investigation accuracy (25%), agentic design (15%), innovation (15%), explainability (10%), demo quality (10%). The live part leads with the uncertain case, because that's what the brief is about.

## Before you press record (10 min)

1. Savanna console: workspace shows **Active**.
2. PowerShell, in the project folder with the venv active: `python -m streamlit run ui/app.py`
3. Browser full screen at 90% zoom. Tabs open: **(1)** SentinelGraph, **(2)** Savanna GraphStudio (Explore Graph on FraudGraph).
4. Warm-up: run any case once so TigerGraph and Gemini are awake, then click **Investigate** to reset.
5. Close notifications. Recorder: Win+Alt+R (Xbox Game Bar) or OBS, mic on.
6. Keep this script on your phone. Speak slowly; pauses are fine.

---

## 0:00 to 0:15 · Intro (Investigate page, empty "Ready to investigate" screen)
> "Hi, I'm Nirmal Joseph, and this is SentinelGraph, my submission for the TigerGraph Agentic Fraud Investigation task at Hacker House Goa 2026. It's an AI agent that investigates fraud alerts on TigerGraph and recommends the next best action, even when the signals are uncertain."

## 0:15 to 0:40 · The problem and the approach (stay on the same screen)
> "In this bank's own history, every one of the 900 alerts raised by the risk score alone was a false alarm. So the score is a reason to look, not a verdict. The agent works like a careful analyst: it pulls evidence from the graph, says what it doesn't know, asks for the one piece of evidence that would settle it, and only then recommends an action, with the right person approving it."

## 0:40 to 1:55 · LIVE: an uncertain case, HHG-003
Pick **HHG-003** in the alert box. Point at the alert text.
> "A customer says they never made this $49 purchase."

Click **Run investigation**. While the steps stream in:
> "Each line is a GSQL query through the TigerGraph MCP server, about a tenth of a second each: the card's history, the device, other cards, and similar closed cases through vector search."

When it finishes, point at the green **Live run** bar.
> "That was live, and the case is now written back into TigerGraph."

Point at the four cards across the top.
> "What happened, what the agent found, how certain it is, and what happens next."

Scroll to **Decision evolution**.
> "At first look the graph evidence says normal use: probability about 17%. That's not enough to block someone's card, so the agent's first recommendation was to verify with the customer. The customer confirms they didn't make it, which moves it to 63%. The recommendation updates: block the card to protect the customer."

Scroll up to **Why the agent handed over?**.
> "But the denial and the graph still disagree, so the agent doesn't fake confidence. It marks the case uncertain and escalates to an analyst, as the policy says."

Point at the **Next best action** panel: action hierarchy and governance.
> "Opening the case runs automatically. Blocking the card needs a team lead."

Click **Approve** on BLOCK_CARD.
> "The approval is written into the case's audit trail in the graph."

## 1:55 to 2:45 · Fraud the card view can't see: HHG-019
Sidebar **Case Portfolio**, then click **HHG-019** (opens as a Saved investigation).
> "Here's the portfolio: 20 alerts, 10 legitimate, 9 fraud, 1 uncertain. HHG-019 is a $99.92 online purchase that looks ordinary on its own card."

Scroll to the **Investigation graph**.
> "The graph shows the same rare device on four other cards within days, all with near-identical amounts and high scores from our case-memory model. That model is trained on the bank's closed cases and beats the bank's own score: AUC 0.91 against 0.87."

Scroll up to **Why the agent stopped?**.
> "Two independent lines of evidence agree above 85%, so the agent stops and acts: block the card, monitor the four connected cards, and file a suspicious activity report for the fraud manager to approve."

Click the **Suspicious activity report** tab for two seconds.

## 2:45 to 3:15 · Finding fraud nobody reported (custom alert)
Back to **Investigate**. Switch **LLM investigator** off (faster on camera). Open **Custom alert**: transaction **3475414**, trigger **analyst_request**, then click **Investigate custom alert**.
> "The agent also scans the graph on its own. This alert came from that scan: four purchases in half an hour, each just under $500. The graph finds the same pattern on 11 other cards, and case memory matches it to undocumented September cases. It's not one of the five known patterns, so the agent labels it undocumented, files a report and escalates."

## 3:15 to 3:35 · Memory and policy grounding (Policies page)
Sidebar **Policies**, then type *when may the agent block a card without approval?*
> "The fraud policy lives in TigerGraph as vectors too. This is the GraphRAG context the LLM gets: the exact clause, not raw data. And the answer is never: blocking always needs a human."

## 3:35 to 3:55 · Close (Savanna tab)
Show the `FraudCase` vertices with their edges to transactions, cards and events.
> "Every case goes back into TigerGraph as memory, linked to its transactions, cards and decisions, so the next investigation can find it. Same evidence, same decision: all 20 answers reproduce exactly. The code, the answer files and the full traces are on GitHub. Thanks for watching."

---

## If something goes wrong while recording
- **A run hangs for more than 20 seconds:** switch LLM investigator off and run again. Don't restart the recording.
- **"TigerGraph unreachable":** the workspace is waking up. Wait a minute, reload, continue.
- **You stumble on a line:** pause, then repeat the sentence. You can trim it later, or just leave it.
- **Running long:** cut the Policies section (3:15 to 3:35) first.
