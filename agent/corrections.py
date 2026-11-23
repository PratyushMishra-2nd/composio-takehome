"""Correction layer applied after verification, in build.py. Every change is recorded (app, field,
from, to, source, reason) and shown on the page, so nothing is silently edited.

Sources:
  adjudication  - the third check ruled the agent wrong on a sample disagreement (ruling reference/neither)
  rule          - the project's own definitions, enforced uniformly on all 100 apps
  human         - a judgment call by the author, with the reason written down
Accuracy numbers on the page are measured BEFORE these corrections (otherwise the sample would score itself).
"""
import re

HUMAN = [
    # (app id, field, new value, reason)
    (98, "composio_in_catalog", False,
     "Composio's router matched 'mermaid_chart_mcp', which is Mermaid Chart (hosted SaaS), a different product from the open-source Mermaid CLI."),
]

VERDICT_ORDER = ["build_now", "build_with_caveat", "needs_outreach", "not_buildable"]


def apply(apps, adjudication):
    changes = []
    by_id = {a["id"]: a for a in apps}

    def setf(a, field, new, source, reason):
        old = a[field] if field in a else None
        if old == new:
            return
        a[field] = new
        changes.append({"id": a["id"], "app": a["app"], "field": field, "from": old, "to": new, "source": source, "reason": reason})

    # 1. third-check rulings on sample disagreements
    fmap = {"auth": "auth_methods", "access": "access", "verdict": "verdict"}
    for key, r in adjudication.items():
        i, field = key.split(":")
        if r.get("ruling") not in ("reference", "neither") or field not in fmap:
            continue
        val = r["correct_value"]
        if field == "auth":
            val = sorted(x.strip(" '\"") for x in re.split(r"[;,\[\]]", val) if x.strip(" '\""))
        setf(by_id[int(i)], fmap[field], val, "adjudication", r.get("reason", "")[:300])

    # 2. uniform rules from the project's own definitions
    for a in apps:
        blk = (a["blocker"] or "").lower()
        if a["access"].startswith("self_serve") and re.search(r"app review|review/assessment|requested manually|manual(ly)? approv", blk):
            setf(a, "access", "admin_approval", "rule", "Blocker text names a vendor review/approval before other users can connect; the gate field must say so.")
        sandbox = (a.get("extras") or {}).get("sandbox")
        if a["access"] in ("customer_account", "partner_gated") and sandbox != "free" and a["verdict"] in ("build_now", "build_with_caveat"):
            setf(a, "verdict", "needs_outreach", "rule", f"Definition: {a['access']} without a free developer sandbox => needs_outreach (sandbox: {sandbox}).")
        if a["access"] in ("self_serve_trial", "paid_plan", "admin_approval") and a["verdict"] == "build_now":
            setf(a, "verdict", "build_with_caveat", "rule", f"Definition: build_now needs ongoing self-serve credentials; access={a['access']} is a caveat.")
        if a["access"] == "self_serve_free" and a["verdict"] == "build_with_caveat" and not blk.strip():
            pass  # leave: caveat may come from API breadth

    # 3. evidence floor: answers with almost no confirmed evidence are flagged, not trusted
    for a in apps:
        ev = a["evidence"]
        ok = sum(1 for e in ev if e.get("status") == "verified")
        a["evidence_weak"] = len(ev) >= 3 and ok <= 1
        if a["evidence_weak"]:
            changes.append({"id": a["id"], "app": a["app"], "field": "evidence", "from": f"{ok}/{len(ev)} quotes confirmed", "to": "flagged unverified",
                            "source": "rule", "reason": "At most one cited quote could be confirmed on its page; excluded from headline quick-win lists."})

    # 4. human judgment calls
    for i, field, new, reason in HUMAN:
        a = by_id[i]
        if field == "composio_in_catalog":
            if a["composio"]["in_catalog"] != new:
                changes.append({"id": i, "app": a["app"], "field": "in Composio", "from": a["composio"]["in_catalog"], "to": new, "source": "human", "reason": reason})
                a["composio"]["in_catalog"] = new
                a["composio"]["toolkits"] = []
    return changes
