"""Correction layer applied after verification, in build.py. Every change is recorded (app, field,
from, to, source, reason) and shown on the page, so nothing is silently edited.

Sources:
  adjudication  - the third check ruled the agent wrong on a sample disagreement (ruling reference/neither)
  rule          - the project's own definitions, enforced uniformly on all 100 apps
  distribution  - narrow per-app check of vendor review / install caps, applied only when its quote is confirmed
  hand          - the author's hand check of the 20 sample apps against vendor docs (final for those apps)
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


def apply(apps, adjudication, distribution=None, gold=None):
    distribution = distribution or {}
    gold = gold or {}  # hand-checked reference rows, keyed by id
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
        g = gold.get(int(i))
        if g is not None and field in ("access", "verdict") and g.get(field, "").strip() and g[field].strip() != val:
            continue  # the human hand check disagrees with the third check: the human wins
        setf(by_id[int(i)], fmap[field], val, "adjudication", r.get("reason", "")[:300])

    # 1b. hand check: on the 20 sample apps the hand-checked reference is final (accuracy was measured before this)
    for i, g in gold.items():
        a = by_id.get(i)
        if not a:
            continue
        hauth = sorted(x.strip() for x in g.get("auth_methods", "").split(";") if x.strip())
        if hauth and sorted(a["auth_methods"]) != hauth:
            setf(a, "auth_methods", hauth, "hand", "Hand-checked against vendor docs: " + (g.get("notes") or "")[:220])
        for f in ("access", "verdict"):
            v = (g.get(f) or "").strip()
            if v:
                setf(a, f, v, "hand", "Hand-checked against vendor docs: " + (g.get("notes") or "")[:220])
        for f in ("mcp_exists", "mcp_official"):
            v = (g.get(f) or "").strip().lower()
            if v in ("yes", "no"):
                setf(a, f, v == "yes", "hand", "Hand-checked against vendor docs.")
        a["hand_checked"] = True

    # 2. uniform rules from the project's own definitions (never override a hand-checked app)
    for a in apps:
        if a.get("hand_checked"):
            continue
        blk = (a["blocker"] or "").lower()
        if a["access"].startswith("self_serve") and re.search(r"app review|review/assessment|requested manually|manual(ly)? approv", blk):
            setf(a, "access", "admin_approval", "rule", "Blocker text names a vendor review/approval before other users can connect; the gate field must say so.")
        sandbox = (a.get("extras") or {}).get("sandbox")
        if a["access"] in ("customer_account", "partner_gated") and sandbox != "free" and a["verdict"] in ("build_now", "build_with_caveat"):
            setf(a, "verdict", "needs_outreach", "rule", f"Definition: {a['access']} without a free developer sandbox => needs_outreach (sandbox: {sandbox}).")
        free_path = "self-host" in (a["access_detail"] or "").lower() and "free" in (a["access_detail"] or "").lower()
        if a["access"] in ("self_serve_trial", "paid_plan", "admin_approval") and a["verdict"] == "build_now" and not free_path:
            setf(a, "verdict", "build_with_caveat", "rule", f"Definition: build_now needs ongoing self-serve credentials; access={a['access']} is a caveat.")
        if a["access"] == "self_serve_free" and a["verdict"] == "build_with_caveat" and not blk.strip():
            pass  # leave: caveat may come from API breadth

    # 2b. distribution check (evidence-gated): vendor review or install cap before other customers can connect
    for a in apps:
        d = distribution.get(a["id"])
        if not d or d.get("quote_status") != "verified" or d["gate"] not in ("install_cap", "review_required"):
            continue
        what = f"unreviewed apps capped at {d['install_cap']} installs" if d["gate"] == "install_cap" and d.get("install_cap") else d["gate"].replace("_", " ")
        reason = f"Distribution check, quote confirmed on {d['url']}: \"{d['quote'][:160]}\" ({what})."
        if a["access"].startswith("self_serve"):
            setf(a, "access", "admin_approval", "distribution", reason)
        if a["verdict"] == "build_now":
            setf(a, "verdict", "build_with_caveat", "distribution", reason)

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
