"""Keep the approval-tracker issues in step with the final data: rewrite each issue's body and its
gate/verdict/composio labels from docs/data.json (uses gh; issues were created via Composio).
Usage: python agent/sync_tracker.py"""
import json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outreach import body  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPO = "PratyushMishra-2nd/composio-takehome"
D = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
A = {a["id"]: a for a in D["apps"]}
cat = json.loads((ROOT / "results" / "composio_catalog.json").read_text(encoding="utf-8"))
for k, a in A.items():  # catalog view after corrections (e.g. Mermaid)
    cat.setdefault(str(k), {})["in_composio"] = a["composio"]["in_catalog"]
    cat[str(k)]["matched_toolkits"] = a["composio"]["toolkits"]
issues = json.loads((ROOT / "results" / "outreach_issues.json").read_text(encoding="utf-8"))
for i, v in issues.items():
    a = A[int(i)]
    num = v["url"].rsplit("/", 1)[1]
    have = {l["name"] for l in json.loads(subprocess.run(["gh", "issue", "view", num, "-R", REPO, "--json", "labels"],
                                                         capture_output=True, text=True).stdout)["labels"]}
    want = {f"gate:{a['access']}", f"verdict:{a['verdict']}", "composio:listed" if a["composio"]["in_catalog"] else "composio:gap"}
    stale = {l for l in have if l.split(":")[0] in ("gate", "verdict", "composio") and l not in want}
    cmd = ["gh", "issue", "edit", num, "-R", REPO, "--body", body(a, cat),
           "--title", f"[{a['category']}] {a['app']}: {a['access'].replace('_', ' ')} before toolkit can ship"]
    for l in want - have:
        cmd += ["--add-label", l]
    for l in stale:
        cmd += ["--remove-label", l]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(num, a["app"], "ok" if r.returncode == 0 else r.stderr[:120])
