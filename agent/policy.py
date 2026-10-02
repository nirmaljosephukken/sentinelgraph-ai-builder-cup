"""
Deterministic policy engine: Fraud Policy v1.0 as code.

The LLM may suggest, but only this module decides which actions are recommended, in what order, under which
rule, and with which approval route. It also enforces permissions (only `auto` actions may be executed by the
agent; L1/L2 actions are queued for a human) and checks every recommendation for policy breaches
(e.g. R1 block on a single weak signal, R10 BLOCK_ALL_CARDS without two compromised cards).
"""
from __future__ import annotations

from dataclasses import dataclass, field

AUTO = {"ALLOW_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS", "WARN_CUSTOMER", "VERIFY_WITH_CUSTOMER",
        "STEP_UP_AUTH", "GENERATE_REPORT", "CREATE_CASE", "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD"}
ORDER = ["DECLINE_TRANSACTION", "BLOCK_CARD", "BLOCK_ALL_CARDS", "ALLOW_TRANSACTION", "CREATE_CASE",
         "STEP_UP_AUTH", "VERIFY_WITH_CUSTOMER", "MONITOR_CARD", "FILE_REPORT", "MONITOR_CONNECTED_CARDS",
         "ESCALATE_TO_ANALYST", "WARN_CUSTOMER", "GENERATE_REPORT", "CLOSE_NO_FRAUD"]


def route(action: str, exposure: float) -> str:
    if action in AUTO:
        return "auto"
    if action == "DECLINE_TRANSACTION":
        return "L1"
    if action == "BLOCK_CARD":
        return "L1" if exposure <= 2500 else "L2"
    return "L2"  # BLOCK_ALL_CARDS, FILE_REPORT


@dataclass
class Situation:
    trigger: str
    p: float                     # current fraud probability
    fraud_families: int
    legit_families: int
    exposure: float
    pattern: str
    recurring_dispute: bool = False
    card_testing: bool = False
    testing_large_over_100: bool = False
    shared_origin: bool = False          # shared device / ring / connected other-card fraud (R6, R2 report)
    link_summary: str = ""               # how the connected cards are linked, from the evidence (agent/linkage.py)
    coordinated_undocumented: bool = False  # R9
    connected_cards: int = 0
    compromised_cards_of_customer: int = 1
    response: str | None = None          # denied | confirmed | no_reply | None
    flagged_pending: bool = True         # risk-score alerts: the flagged authorisation is still pending
    online: bool = True


@dataclass
class Decision:
    actions: list[dict] = field(default_factory=list)
    request: str | None = None           # customer_validation | step_up_auth | analyst_info
    request_reason: str = ""
    stop: bool = False
    verdict: str = "uncertain"
    status: str = "open"
    sar: bool = False
    sar_reason: str = ""
    notes: list[str] = field(default_factory=list)


class Plan:
    def __init__(self, exposure: float):
        self.exposure = exposure
        self.items: dict[str, str] = {}

    def add(self, action: str, reason: str):
        if action in self.items:
            if reason not in self.items[action]:
                self.items[action] += "; " + reason
        else:
            self.items[action] = reason

    def out(self) -> list[dict]:
        return [{"action": a, "route": route(a, self.exposure), "reason": self.items[a]}
                for a in sorted(self.items, key=ORDER.index)]


def sar_decision(s: Situation, fraud: bool) -> tuple[bool, str]:
    if not fraud:
        return False, "No report: activity not confirmed or strongly suspected as fraud (policy 3a)."
    why = []
    if s.exposure > 1000:
        why.append(f"exposure ${s.exposure:,.2f} exceeds $1,000")
    if s.shared_origin:
        why.append(f"the activity is linked to fraud on {s.connected_cards} other card(s) ({s.link_summary})"
                   if s.link_summary else f"the activity is linked to fraud on {s.connected_cards} other card(s)")
    if s.coordinated_undocumented:
        why.append("the pattern is coordinated and undocumented (R9)")
    if why:
        return True, "File (policy 3a" + (", R6" if s.shared_origin else "") + (", R9" if s.coordinated_undocumented else "") + \
            "): fraud confirmed or strongly suspected and " + "; ".join(why) + "."
    return False, (f"No report (policy 3a): fraud is confirmed but exposure ${s.exposure:,.2f} is under $1,000, no "
                   f"link to fraud on other cards and the pattern is documented. Case only.")


def fraud_actions(s: Situation, plan: Plan, rule: str) -> None:
    """Containment + record + reporting for fraud that is confirmed or strongly suspected."""
    if s.card_testing and not s.testing_large_over_100:
        plan.add("DECLINE_TRANSACTION", "R5: card-testing sequence, decline pending authorisations")
        plan.add("STEP_UP_AUTH", "R5: require one-time passcode before further activity")
    else:
        why = {"R2": "R2: cardholder denies the activity", "R5": "R5: card testing with a purchase over $100 already cleared",
               "STRONG": "Fraud probability >= 0.85 on two or more independent lines of evidence (policy 6)"}[rule]
        plan.add("BLOCK_CARD", f"{why}; exposure ${s.exposure:,.2f} "
                              f"{'<= $2,500 -> L1' if s.exposure <= 2500 else '> $2,500 -> L2'}")
    if s.compromised_cards_of_customer >= 2:
        plan.add("BLOCK_ALL_CARDS", "R10: two or more of the customer's cards show confirmed fraud")
    plan.add("CREATE_CASE", ("R2" if rule == "R2" else "Policy 3a") + ": record the investigation and write it to the graph")
    if s.connected_cards:
        plan.add("MONITOR_CONNECTED_CARDS", f"R6: {s.connected_cards} other card(s) are linked to this activity"
                                            + (f" ({s.link_summary})" if s.link_summary else ""))
    sar, why = sar_decision(s, True)
    if sar:
        plan.add("FILE_REPORT", why.replace("File (", "").rstrip(".").replace("): ", ": ", 1))
    if s.coordinated_undocumented:
        plan.add("ESCALATE_TO_ANALYST", "R9: undocumented coordinated pattern, analyst review of the wider scheme")


def decide(s: Situation) -> Decision:
    d = Decision()
    plan = Plan(s.exposure)

    # ------------------------------------------------ after evidence came back
    if s.response is not None:
        if s.recurring_dispute:
            if s.response == "confirmed":
                plan.add("CREATE_CASE", "R7/R3: dispute recorded; charge matches the cardholder's recurring pattern")
                plan.add("WARN_CUSTOMER", "R7: recurring-charge reminder sent to the cardholder")
                plan.add("CLOSE_NO_FRAUD", "R3: cardholder recognised the recurring charge; confirmation noted in the case")
                d.verdict, d.status = "legitimate", "closed_legitimate"
            else:
                plan.add("CREATE_CASE", "R7: dispute on a recurring charge")
                plan.add("ESCALATE_TO_ANALYST", "R8: recurring pattern conflicts with the cardholder's denial")
                plan.add("MONITOR_CARD", "R4/R8: keep the card active under monitoring pending review")
                d.verdict, d.status = "uncertain", "escalated"
        elif s.response == "denied":
            fraud_actions(s, plan, "R2" if not s.card_testing else ("R5" if s.testing_large_over_100 else "R2"))
            if s.p >= 0.70:
                d.verdict = "fraud"
            else:
                d.verdict = "uncertain"
                plan.add("ESCALATE_TO_ANALYST", f"R8: the cardholder's denial conflicts with graph evidence of normal "
                                                f"use (probability {s.p:.2f}); analyst to confirm while the card is blocked")
            d.status = "escalated" if "ESCALATE_TO_ANALYST" in plan.items else "closed_fraud"
        elif s.response == "confirmed":
            if s.trigger == "risk_score":
                plan.add("ALLOW_TRANSACTION", "R3: cardholder confirmed the transaction")
            plan.add("CREATE_CASE", "Policy 3a: case opened when evidence was requested; closed as legitimate")
            plan.add("CLOSE_NO_FRAUD", "R3: cardholder confirmed; confirmation noted in the case file")
            d.verdict, d.status = "legitimate", "closed_legitimate"
        else:  # no_reply
            plan.add("MONITOR_CARD", "R4: no reply within 24 hours")
            if s.flagged_pending:
                plan.add("DECLINE_TRANSACTION", "R4: decline pending authorisations while unverified")
            plan.add("CREATE_CASE", "Policy 3a: evidence requested")
            if s.exposure > 500:
                plan.add("ESCALATE_TO_ANALYST", f"R4/R8: unresolved and exposure ${s.exposure:,.2f} > $500")
            d.verdict = "uncertain"
            d.status = "escalated" if s.exposure > 500 else "open"
        d.actions = plan.out()
        d.sar = any(a["action"] == "FILE_REPORT" for a in d.actions)
        d.sar_reason = sar_decision(s, d.verdict == "fraud")[1]
        d.stop = True
        return d

    # ------------------------------------------------ initial recommendation
    strong_fraud = s.p >= 0.85 and s.fraud_families >= 2
    strong_legit = s.p <= 0.15 and s.legit_families >= 2
    if s.recurring_dispute:
        plan.add("CREATE_CASE", "R7 and 3a: a customer dispute always opens a case")
        plan.add("VERIFY_WITH_CUSTOMER", "R7: charge matches the cardholder's own recurring pattern; confirm before any block")
        plan.add("WARN_CUSTOMER", "R7: send a recurring-charge reminder")
        d.request, d.request_reason = "customer_validation", (
            "The disputed charge repeats the cardholder's own recurring pattern (same amount, product, region), "
            "which conflicts with the denial. R7 says verify and do not block.")
    elif strong_fraud:
        fraud_actions(s, plan, "R5" if (s.card_testing and s.testing_large_over_100) else
                      ("R2" if s.trigger == "customer_report" else "STRONG"))
        d.verdict = "fraud"
        d.status = "escalated" if "ESCALATE_TO_ANALYST" in plan.items else "closed_fraud"
        d.stop = True
    elif strong_legit:
        if s.trigger == "risk_score":
            plan.add("ALLOW_TRANSACTION", "Policy 6: probability <= 0.15 on two independent lines of evidence")
        plan.add("GENERATE_REPORT", "Internal write-up of the review; no case needed (probability < 0.30, no dispute)")
        plan.add("CLOSE_NO_FRAUD", "Policy 6: stop, the evidence supports a legitimate transaction")
        d.verdict, d.status, d.stop = "legitimate", "closed_legitimate", True
    else:
        if s.card_testing:
            plan.add("DECLINE_TRANSACTION", "R5: card-testing sequence observed")
            plan.add("STEP_UP_AUTH", "R5: confirm the cardholder before further activity")
            d.request = "step_up_auth"
            d.request_reason = "Card-testing sequence found; step-up authentication shows whether the cardholder is present."
        elif s.trigger == "customer_report":
            plan.add("VERIFY_WITH_CUSTOMER", f"R1: probability {s.p:.2f} < 0.85 and the graph evidence does not yet confirm "
                                            f"the denial; confirm card possession and the disputed details before blocking")
            plan.add("MONITOR_CARD", "Raise monitoring while the cardholder confirms")
            d.request = "customer_validation"
            d.request_reason = ("The cardholder's report is the main evidence; the graph does not independently confirm it. "
                                "Confirming possession of the card and the disputed details settles R2 vs R3.")
        else:
            online = s.online
            if s.p >= 0.70 and s.flagged_pending:
                plan.add("DECLINE_TRANSACTION", f"Probability {s.p:.2f} >= 0.70: hold the pending authorisation (L1)")
            action = "STEP_UP_AUTH" if (online and s.trigger == "risk_score" and s.p < 0.5) else "VERIFY_WITH_CUSTOMER"
            if s.p < 0.15:
                plan.add(action, f"Policy 6 / R1: probability {s.p:.2f} is low but rests on only {max(1, s.legit_families)} "
                                 f"independent line(s) of evidence; confirm with the cardholder before closing")
            else:
                plan.add(action, f"R1: probability {s.p:.2f} rests on {max(1, s.fraud_families)} weak signal(s); "
                                 f"verify before any block")
            plan.add("MONITOR_CARD", "Monitor for 72h while verification is pending")
            d.request = "step_up_auth" if action == "STEP_UP_AUTH" else "customer_validation"
            d.request_reason = (f"Probability {s.p:.2f} is between the stop thresholds (0.15 / 0.85) and the case rests on "
                                f"too few independent signals to act; the cardholder's answer is the highest-value evidence.")
        if s.p >= 0.30 or d.request or s.trigger == "customer_report":
            plan.add("CREATE_CASE", "Policy 3a: probability >= 0.30, evidence requested or customer dispute")
        if s.connected_cards and s.p >= 0.5:
            plan.add("MONITOR_CONNECTED_CARDS", f"R6: {s.connected_cards} linked card(s) under monitoring meanwhile")
        if s.p > 0.3 and s.exposure > 500 and s.fraud_families >= 1 and s.legit_families >= 1:
            plan.add("ESCALATE_TO_ANALYST", "R8: evidence conflicts and exposure > $500")
        d.verdict = "uncertain" if s.p > 0.3 else "legitimate"
        d.status = "open"
    d.actions = plan.out()
    d.sar = any(a["action"] == "FILE_REPORT" for a in d.actions)
    d.sar_reason = sar_decision(s, d.verdict == "fraud")[1]
    return d


def check(actions: list[dict], s: Situation) -> list[str]:
    """Policy guard: returns breaches (empty list = compliant)."""
    names = [a["action"] for a in actions]
    out = []
    if "BLOCK_CARD" in names and s.p < 0.70 and s.fraud_families <= 1 and s.response != "denied":
        out.append("R1 breach: BLOCK_CARD on a single weak signal below 0.70")
    if "BLOCK_ALL_CARDS" in names and s.compromised_cards_of_customer < 2:
        out.append("R10 breach: BLOCK_ALL_CARDS without two compromised cards")
    if s.recurring_dispute and "BLOCK_CARD" in names:
        out.append("R7 breach: blocking on a disputed recurring charge")
    for a in actions:
        if a["route"] != route(a["action"], s.exposure):
            out.append(f"routing error on {a['action']}")
    return out


def executable(actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split into actions the agent may execute now (auto) and ones queued for human approval."""
    return [a for a in actions if a["route"] == "auto"], [a for a in actions if a["route"] != "auto"]
