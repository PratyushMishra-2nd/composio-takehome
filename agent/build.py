"""Merge passes + verification into docs/data.json (the single file the HTML page reads,
and the machine-readable export for agents).
Usage: python agent/build.py"""
import json, time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_pass(name):
    d = ROOT / "results" / name
    return {int(p.stem): json.loads(p.read_text(encoding="utf-8")) for p in d.glob("[0-9][0-9][0-9].json")} if d.exists() else {}


def load_json(path, default):
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def quote_stats(v):
    q = [x for c in v.values() for x in c["quotes"]]
    c = Counter(x["status"] for x in q)
    return {"total": len(q), **{k: c.get(k, 0) for k in ("verified", "not_found", "unreadable", "fetch_failed")}}


def main():
    p1, p3 = load_pass("pass1"), {**load_pass("pass3"), **load_pass("pass4")}
    p2 = {**load_pass("pass2"), **p3}  # latest re-research wins
    v1 = load_json("results/verify_pass1.json", {})
    vf = load_json("results/verify_final.json", {})
    redo = load_json("results/redo_pass1.json", {})
    redo2 = load_json("results/redo_pass2.json", {})  # claim-coverage round, re-researched in pass 3
    redo3 = load_json("results/redo_gate_audit.json", {})  # gate audit on every self-serve app, pass 4
    acc = load_json("results/accuracy.json", None)
    cat = load_json("results/composio_catalog.json", {})
    issues = load_json("results/outreach_issues.json", {})
    ex_dir = ROOT / "results" / "extras"
    extras = {int(f.stem): json.loads(f.read_text(encoding="utf-8"))["result"] for f in ex_dir.glob("[0-9][0-9][0-9].json")} if ex_dir.exists() else {}
    vx = load_json("results/verify_extras.json", {})
    human = load_json("results/human_review.json", {})

    apps = []
    for i in sorted(p1):
        rec = p2.get(i, p1[i])
        r = rec["result"]
        ver = vf.get(str(i)) or v1.get(str(i)) or {}
        changed = []
        if i in p2:
            a, b = p1[i]["result"], p2[i]["result"]
            for k in ("auth_methods", "access", "mcp_exists", "mcp_official", "verdict", "api_breadth"):
                if (sorted(a[k]) if isinstance(a[k], list) else a[k]) != (sorted(b[k]) if isinstance(b[k], list) else b[k]):
                    changed.append({"field": k, "from": a[k], "to": b[k]})
        apps.append({
            "id": i, "app": rec["app"], "category": rec["category"], "hint": rec["hint"],
            **{k: r[k] for k in ("description", "auth_methods", "auth_detail", "access", "access_detail", "api_types",
                                 "api_breadth", "api_notes", "mcp_exists", "mcp_official", "mcp_url", "verdict", "blocker", "confidence")},
            "evidence": ver.get("quotes") or [dict(e, status="unchecked") for e in r["evidence"]],
            "checks": {"apis_guru": ver.get("apis_guru"), "mcp_registry": ver.get("mcp_registry")},
            "open_issues": [{"type": t, "field": f, "msg": m} for t, f, m in ver.get("issues", [])],
            "flagged_pass1": str(i) in redo or str(i) in redo2 or str(i) in redo3,
            "flag_reasons": "\n".join(x for x in (redo.get(str(i), ""), redo2.get(str(i), ""), redo3.get(str(i), "")) if x),
            "rounds": 1 + (str(i) in redo) + (str(i) in redo2) + (str(i) in redo3),
            "rechecked": i in p2,
            "changed": changed,
            "human": human.get(str(i)),
            "composio": {"in_catalog": cat.get(str(i), {}).get("in_composio"), "toolkits": cat.get(str(i), {}).get("matched_toolkits", []),
                         "tools": (cat.get(str(i), {}).get("primary_tools", []) + cat.get(str(i), {}).get("related_tools", []))[:6]},
            "tracker_issue": (issues.get(str(i)) or {}).get("url"),
            "extras": (lambda x, v: x and {
                "webhooks": x["webhooks"]["available"], "webhooks_detail": x["webhooks"]["detail"],
                "sandbox": x["sandbox"]["available"], "sandbox_detail": x["sandbox"]["detail"],
                "rate_limits": x["rate_limits"]["summary"] if x["rate_limits"]["documented"] else "not documented",
                "sdks": x["sdks"]["official"],
                "spec": x["openapi_spec"]["available"], "spec_url": x["openapi_spec"]["url"],
                "spec_confirmed": (v or {}).get("spec_confirmed"), "spec_check": (v or {}).get("spec_check"),
                "apis_guru_spec": (v or {}).get("apis_guru_spec"), "confidence": x["confidence"],
                "evidence": [dict(q, field=f) for f, q in ((v or {}).get("quotes") or {k: dict(x[k]["evidence"], status="unchecked", note="") for k in ("webhooks", "sandbox", "rate_limits", "sdks", "openapi_spec")}).items()],
                "issues": [{"type": t, "field": f, "msg": m} for t, f, m in (v or {}).get("issues", [])],
            })(extras.get(i), vx.get(str(i))),
            "seconds": rec.get("seconds"),
        })

    # ---- corrections (after verification; accuracy is measured before these) ----
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "agent"))
    from corrections import apply as apply_corrections
    dist_dir = ROOT / "results" / "distribution"
    distribution = {int(f.stem): json.loads(f.read_text(encoding="utf-8"))["result"] for f in dist_dir.glob("[0-9][0-9][0-9].json")} if dist_dir.exists() else {}
    gold_rows = {int(r["id"]): r for r in __import__("csv").DictReader(open(ROOT / "data" / "gold.csv", encoding="utf-8"))}
    corrections = apply_corrections(apps, load_json("results/adjudication.json", {}), distribution, gold_rows)

    # official MCP: "confirmed" only with independent support
    def _mcp_confirmed(a):
        reg = ((a["checks"].get("mcp_registry") or {}).get("official") or [])
        dom = a["hint"].split()[0].lower().replace("https://", "").replace("http://", "").split("/")[0]
        base = ".".join(dom.split(".")[-2:])
        ev_ok = any(e["field"] == "mcp" and e.get("status") == "verified" and base and base in e["url"] for e in a["evidence"])
        return bool(reg) or (bool(base) and base in (a["mcp_url"] or "") and ev_ok)
    for a in apps:
        a.setdefault("hand_checked", False)
        a["mcp_official_confirmed"] = a["mcp_official"] and _mcp_confirmed(a)

    # ---- patterns ----
    n = len(apps)
    auth_c = Counter(m for a in apps for m in a["auth_methods"])
    access_c = Counter(a["access"] for a in apps)
    verdict_c = Counter(a["verdict"] for a in apps)
    by_cat = defaultdict(lambda: Counter())
    for a in apps:
        by_cat[a["category"]][a["verdict"]] += 1
        by_cat[a["category"]]["_" + a["access"]] += 1
        by_cat[a["category"]]["_n"] += 1
        by_cat[a["category"]]["_mcp"] += a["mcp_exists"]
        by_cat[a["category"]]["_oauth"] += "oauth2" in a["auth_methods"]
    patterns = {
        "n": n,
        "auth": auth_c.most_common(),
        "oauth_only": sum(1 for a in apps if a["auth_methods"] == ["oauth2"]),
        "key_only": sum(1 for a in apps if set(a["auth_methods"]) <= {"api_key", "bearer_token", "basic"} and a["auth_methods"]),
        "both": sum(1 for a in apps if "oauth2" in a["auth_methods"] and set(a["auth_methods"]) & {"api_key", "bearer_token", "basic"}),
        "access": access_c.most_common(),
        "verdict": verdict_c.most_common(),
        "mcp_any": sum(a["mcp_exists"] for a in apps),
        "mcp_official": sum(a["mcp_official"] for a in apps),
        "composio_listed": sum(1 for a in apps if a["composio"]["in_catalog"]),
        "mcp_official_confirmed": sum(1 for a in apps if a["mcp_official_confirmed"]),
        "evidence_weak": [a["app"] for a in apps if a["evidence_weak"]],
        "composio_gaps": [{"id": a["id"], "app": a["app"], "category": a["category"], "verdict": a["verdict"], "access": a["access"], "blocker": a["blocker"], "weak": a["evidence_weak"]}
                          for a in sorted(apps, key=lambda a: ["build_now", "build_with_caveat", "needs_outreach", "not_buildable"].index(a["verdict"]))
                          if a["composio"]["in_catalog"] is False],
        "tracker_issues": sum(1 for a in apps if a["tracker_issue"]),
        "extras": (lambda E: E and {
            "n": len(E),
            "webhooks_yes": sum(1 for a in E if a["extras"]["webhooks"] == "yes"),
            "sandbox_free": sum(1 for a in E if a["extras"]["sandbox"] == "free"),
            "sandbox_paid": sum(1 for a in E if a["extras"]["sandbox"] == "paid_or_on_request"),
            "rate_documented": sum(1 for a in E if a["extras"]["rate_limits"] != "not documented"),
            "sdk_any": sum(1 for a in E if a["extras"]["sdks"]),
            "spec_claimed": sum(1 for a in E if a["extras"]["spec"] in ("openapi", "graphql_schema")),
            "spec_confirmed": sum(1 for a in E if a["extras"]["spec_confirmed"]),
            "generatable_build_now": [a["app"] for a in E if a["verdict"] == "build_now" and a["extras"]["spec"] in ("openapi", "graphql_schema")],
            "no_webhooks": [a["app"] for a in E if a["extras"]["webhooks"] == "no"],
            "quotes": dict(Counter(q["status"] for a in E for q in a["extras"]["evidence"])),
            "by_category": {cat: {"webhooks": sum(1 for a in E if a["category"] == cat and a["extras"]["webhooks"] == "yes"),
                                  "sandbox": sum(1 for a in E if a["category"] == cat and a["extras"]["sandbox"] == "free"),
                                  "spec": sum(1 for a in E if a["category"] == cat and a["extras"]["spec"] in ("openapi", "graphql_schema"))}
                            for cat in dict.fromkeys(a["category"] for a in E)},
        })([a for a in apps if a["extras"]]),
        "by_category": {c: dict(v) for c, v in by_cat.items()},
        "blockers": [{"id": a["id"], "app": a["app"], "verdict": a["verdict"], "access": a["access"], "blocker": a["blocker"]}
                     for a in apps if a["verdict"] != "build_now"],
    }

    verification = {
        "pass1_quotes": quote_stats(v1),
        "final_quotes": quote_stats(vf) if vf else None,
        "browser_verified": sum(1 for c in vf.values() for q in c["quotes"] if q.get("note", "").startswith("browser")),
        "pass1_flagged": len(redo),
        "round2_flagged": len(redo2),
        "round2_issue_types": Counter(t for c in load_json("results/verify_round2.json", {}).values() for t, _, _ in c["issues"]).most_common(),
        "flagged_any": len(set(redo) | set(redo2) | set(redo3)),
        "gate_audit": len(redo3),
        "experiment_gate_audit": (lambda e: e and {"apps": len(load_json("results/experiment_gate_audit_redo.json", {})),
                                                 "overall": e["final"]["overall"], "field_accuracy": e["final"]["field_accuracy"]})(load_json("results/experiment_gate_audit_accuracy.json", None)),
        "pass1_issue_types": Counter(t for c in v1.values() for t, _, _ in c["issues"]).most_common(),
        "final_open_issues": Counter(t for c in vf.values() for t, _, _ in c["issues"]).most_common() if vf else None,
        "rechecked": len(p2),
        "changed_apps": sum(1 for a in apps if a["changed"]),
        "changed_fields": sum(len(a["changed"]) for a in apps),
        "accuracy": acc,
        "agent_seconds_total": sum(a["seconds"] or 0 for a in apps),
        "hand_checked": load_json("data/hand_check.json", None),
        "quotes_substantive": (lambda q: {"verified": sum(1 for x in q if x["status"] == "verified" and len(x["quote"].split()) >= 6),
                                          "total": len(q), "short_verified": sum(1 for x in q if x["status"] == "verified" and len(x["quote"].split()) < 6)})(
            [x for c in vf.values() for x in c["quotes"]]),
        "distribution_checked": len(distribution),
    }
    out = {"corrections": corrections, "generated": time.strftime("%Y-%m-%d %H:%M IST"), "patterns": patterns, "verification": verification, "apps": apps}
    (ROOT / "docs").mkdir(exist_ok=True)
    import csv as _csv
    with open(ROOT / "docs" / "apps.csv", "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["id", "app", "category", "description", "auth_methods", "access", "api_types", "api_breadth", "mcp_exists", "mcp_official",
                    "mcp_url", "verdict", "blocker", "in_composio", "composio_toolkits", "tracker_issue",
                    "webhooks", "sandbox", "rate_limits", "official_sdks", "spec", "spec_url", "evidence_urls"])
        for a in apps:
            w.writerow([a["id"], a["app"], a["category"], a["description"], ";".join(a["auth_methods"]), a["access"], ";".join(a["api_types"]),
                        a["api_breadth"], a["mcp_exists"], a["mcp_official"], a["mcp_url"], a["verdict"], a["blocker"],
                        a["composio"]["in_catalog"], ";".join(a["composio"]["toolkits"]), a["tracker_issue"] or "",
                        *((a["extras"]["webhooks"], a["extras"]["sandbox"], a["extras"]["rate_limits"], ";".join(a["extras"]["sdks"]),
                           a["extras"]["spec"], a["extras"]["spec_url"]) if a["extras"] else ("",) * 6),
                        " ".join(sorted({e["url"] for e in a["evidence"]}))])
    (ROOT / "docs" / "data.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"docs/data.json: {n} apps, rechecked {len(p2)}, changed {verification['changed_apps']}")
    print("auth", auth_c.most_common()); print("access", access_c.most_common()); print("verdict", verdict_c.most_common())
    print("mcp any/official", patterns["mcp_any"], patterns["mcp_official"], "composio listed", patterns["composio_listed"])


if __name__ == "__main__":
    main()
