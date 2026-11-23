"""Verifier: independent checks on every research-agent answer. No LLM involved.

Checks per app:
  1. quote      - re-fetch every cited URL and confirm the quoted sentence is really on the page
  2. apis_guru  - compare auth methods with the securitySchemes in the public OpenAPI spec (if APIs.guru has one)
  3. mcp_reg    - compare the MCP claim with the official MCP registry (vendor-namespaced server = official)
  4. composio   - does composio.dev already list a toolkit for this app (cross-check for "buildable")
  5. rules      - internal consistency (e.g. verdict build_now but access partner_gated; low confidence; missing evidence)

Anything that fails becomes a targeted re-research instruction in results/redo_<pass>.json.

Usage: python agent/verify.py --pass pass1 [--final pass2]
"""
import argparse, csv, html, json, re, ssl, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "results" / "cache"
UA = {"User-Agent": "Mozilla/5.0 (research-verifier; composio take-home)"}
CTX = ssl.create_default_context()


def fetch(url, timeout=25):
    key = CACHE / (re.sub(r"[^a-zA-Z0-9]+", "_", url)[:180] + ".txt")
    if key.exists():
        return key.read_text(encoding="utf-8")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            body = r.read(40_000_000).decode("utf-8", "replace")
    except Exception as e:
        body = f"__FETCH_FAILED__ {type(e).__name__}: {e}"
    CACHE.mkdir(parents=True, exist_ok=True)
    key.write_text(body, encoding="utf-8")
    return body


def norm(s):
    s = html.unescape(s)
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\]\([^)]*\)", "]", s)            # markdown link targets
    s = re.sub(r"[*_`#\[\]>|\\]", " ", s)
    s = s.replace("’", "'").replace("“", '"').replace("”", '"').replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def _match(page, q):
    if q and q in page:
        return "verified", ""
    words = q.split()
    if len(words) < 5:
        return "not_found", ""
    grams = [" ".join(words[i:i + 4]) for i in range(len(words) - 3)]
    hit = sum(g in page for g in grams) / len(grams)
    if hit >= 0.7:
        return "verified", f"fuzzy {hit:.0%}"
    return "not_found", f"overlap {hit:.0%}"


def browser_text(url):
    """Text rendered by headless Chromium (verify_browser.py), if that loop has run for this URL."""
    p = ROOT / "results" / "cache_browser" / (re.sub(r"[^a-zA-Z0-9]+", "_", url)[:180] + ".txt")
    return p.read_text(encoding="utf-8") if p.exists() else None


def quote_on_page(quote, url):
    body = fetch(url)
    q = norm(quote)
    if body.startswith("__FETCH_FAILED__"):
        st, note = "fetch_failed", body[17:120]
    elif len(norm(body)) < 400:
        st, note = "unreadable", "page empty or JS-rendered"
    else:
        st, note = _match(norm(body), q)
    if st != "verified":  # second opinion from the browser-rendered page
        bt = browser_text(url)
        if bt and len(bt) > 400:
            bst, bnote = _match(norm(bt), q)
            if bst == "verified":
                return "verified", ("browser-rendered " + bnote).strip()
            if st in ("fetch_failed", "unreadable"):
                return "not_found", ("browser-rendered " + bnote).strip()
    return st, note


# ---------- APIs.guru ----------
_guru = None
def guru_index():
    global _guru
    if _guru is None:
        _guru = json.loads(fetch("https://api.apis.guru/v2/list.json", timeout=60))
    return _guru


def domain_of(hint, app):
    h = hint.split()[0].lower()
    h = re.sub(r"^https?://", "", h).split("/")[0]
    parts = h.split(".")
    base = ".".join(parts[-2:]) if len(parts) >= 2 else ""
    if base in ("github.io", "stoplight.io", ""):
        return ""
    return base


SCHEME_MAP = {"oauth2": "oauth2", "openIdConnect": "oauth2", "apiKey": "api_key"}

def guru_auth(domain):
    if not domain:
        return None
    idx = guru_index()
    keys = [k for k in idx if k == domain or k.startswith(domain + ":")]
    if not keys:
        return None
    k = domain if domain in idx else sorted(keys)[0]
    v = idx[k]
    spec_url = v["versions"][v["preferred"]].get("openapiUrl") or v["versions"][v["preferred"]].get("swaggerUrl")
    try:
        spec = json.loads(fetch(spec_url, timeout=60))
    except Exception:
        return None
    schemes = (spec.get("components", {}) or {}).get("securitySchemes") or spec.get("securityDefinitions") or {}
    out = set()
    for s in schemes.values():
        t = s.get("type")
        if t == "http":
            out.add("basic" if s.get("scheme", "").lower() == "basic" else "bearer_token")
        elif t == "basic":
            out.add("basic")
        elif t in SCHEME_MAP:
            out.add(SCHEME_MAP[t])
    return {"key": k, "spec": spec_url, "auth": sorted(out)}


# ---------- MCP registry ----------
def mcp_registry(app, domain):
    q = urllib.parse.quote(app.split("(")[0].strip())
    body = fetch(f"https://registry.modelcontextprotocol.io/v0/servers?search={q}&limit=50")
    try:
        servers = [s["server"] for s in json.loads(body).get("servers", [])]
    except Exception:
        return None
    rev = ".".join(reversed(domain.split("."))) if domain else None
    official = [s["name"] for s in servers if rev and (s["name"].startswith(rev + "/") or s["name"].startswith(rev + "."))]
    return {"count": len(servers), "official": official, "sample": [s["name"] for s in servers[:5]]}


# ---------- Composio catalog ----------
def composio_has(app):
    # composio.dev/toolkits/<slug> returns 404 for unknown toolkits and a page titled
    # "<App> MCP Server | Composio" for listed ones. Slug is a best-effort guess from the name,
    # so a miss means "not found under the obvious slug", not proof of absence.
    slug = re.sub(r"[^a-z0-9]", "", app.split("(")[0].lower())
    body = fetch(f"https://composio.dev/toolkits/{slug}")
    m = re.search(r"<title>([^<]*)", body)
    listed = bool(m and "| Composio" in m.group(1) and "MCP" in m.group(1))
    return {"slug": slug, "listed": listed, "title": m.group(1).strip() if m else ""}


# ---------- consistency rules ----------
def rules(r):
    issues = []
    fields_with_ev = {e["field"] for e in r["evidence"]}
    for f in ("auth", "access", "api", "mcp"):
        if f not in fields_with_ev:
            issues.append(("missing_evidence", f, f"No evidence cited for {f}."))
        if r["confidence"][f] == "low":
            issues.append(("low_confidence", f, f"Agent marked {f} as low confidence."))
    if r["verdict"] == "build_now" and r["access"] in ("partner_gated", "no_public_api", "admin_approval", "customer_account"):
        issues.append(("contradiction", "verdict", f"Verdict build_now but access={r['access']}."))
    if r["access"] in ("partner_gated", "customer_account") and r["verdict"] in ("build_now", "build_with_caveat") \
            and "sandbox" not in (r["access_detail"] + r["blocker"]).lower():
        issues.append(("contradiction", "verdict", f"access={r['access']} with no developer sandbox mentioned should be needs_outreach, got {r['verdict']}."))
    if TAXONOMY_V1 and r["access"] == "admin_approval":
        issues.append(("taxonomy_revised", "access",
                       "Taxonomy revised after pass 1: 'admin_approval' now means the vendor reviews/verifies the app (or grants a dev token) "
                       "before others can connect. If there is simply no public signup or developer sandbox and credentials only exist "
                       "inside an existing customer account, use 'customer_account' (and verdict needs_outreach unless a free sandbox exists)."))
    if r["access"] == "no_public_api" and r["api_breadth"] in ("broad", "moderate"):
        issues.append(("contradiction", "access", "access=no_public_api but api_breadth is broad/moderate."))
    if r["mcp_official"] and not r["mcp_exists"]:
        issues.append(("contradiction", "mcp", "mcp_official true but mcp_exists false."))
    if r["mcp_exists"] and not r["mcp_url"]:
        issues.append(("missing_evidence", "mcp", "MCP claimed but no URL."))
    return issues


def verify_app(rec):
    r = rec["result"]
    domain = domain_of(rec["hint"], rec["app"])
    checks = {"quotes": [], "issues": []}
    for e in r["evidence"]:
        st, note = quote_on_page(e["quote"], e["url"])
        checks["quotes"].append({**e, "status": st, "note": note})
        if st == "not_found" and e["field"] in ("auth", "access", "mcp"):
            checks["issues"].append(("quote_not_found", e["field"], f"Quote for {e['field']} not found on {e['url']}: \"{e['quote'][:120]}\""))

    g = guru_auth(domain)
    checks["apis_guru"] = g
    if g and g["auth"]:
        agent = set(r["auth_methods"])
        if "oauth2" in g["auth"] and "oauth2" not in agent:
            checks["issues"].append(("source_disagrees", "auth", f"APIs.guru OpenAPI spec ({g['spec']}) declares OAuth2, agent did not list it."))
        if "api_key" in g["auth"] and not agent & {"api_key", "bearer_token", "basic"}:
            checks["issues"].append(("source_disagrees", "auth", f"APIs.guru spec declares an API key scheme, agent listed none."))

    m = mcp_registry(rec["app"], domain)
    checks["mcp_registry"] = m
    if m and m["official"] and not r["mcp_official"]:
        checks["issues"].append(("source_disagrees", "mcp", f"Official MCP registry lists vendor-namespaced server(s) {m['official'][:3]}, agent said no official MCP."))

    c = composio_has(rec["app"])
    checks["composio"] = c
    if c["listed"] and r["verdict"] == "not_buildable":
        checks["issues"].append(("source_disagrees", "verdict", f"Composio already lists a '{c['slug']}' toolkit, agent said not_buildable."))

    # Claim coverage (added after the blind sample showed two error classes): every claimed
    # OAuth2 must be backed by a quote that was found on the page AND mentions OAuth, and must
    # not be the MCP server's login or OAuth 1.0a.
    auth_ev = " ".join(q["quote"] for q in checks["quotes"] if q["field"] == "auth" and q["status"] == "verified").lower()
    detail = r["auth_detail"].lower()
    if "oauth2" in r["auth_methods"]:
        if "oauth" not in auth_ev:
            checks["issues"].append(("unsupported_claim", "auth", "OAuth2 is claimed but no verified auth quote mentions OAuth. Cite the REST API's own OAuth docs, or drop OAuth2 if only the MCP server (or another product) uses it."))
        elif "mcp" in detail:
            checks["issues"].append(("unsupported_claim", "auth", "auth_detail mentions MCP: confirm OAuth2 applies to the public REST/GraphQL API itself, not only to the MCP server login."))
    if "oauth2" in r["auth_methods"] and re.search(r"oauth ?1|1\.0a", detail + " " + auth_ev):
        checks["issues"].append(("unsupported_claim", "auth", "Docs mention OAuth 1.0a: that is a signature scheme (hmac_signature), not OAuth2. Re-check which one the API uses."))
    if r["access"].startswith("self_serve") and re.search(r"no public sign|contact sales|book a demo|sales-led|request access|no free (plan|tier|trial)", r["access_detail"].lower()):
        checks["issues"].append(("contradiction", "access", "access is self-serve but access_detail says signup is sales-led / no public signup: re-check against customer_account / partner_gated / paid_plan."))

    checks["issues"] += rules(r)
    return rec["id"], checks


TAXONOMY_V1 = False  # pass 1 ran before 'customer_account' existed in the schema


def load_pass(name):
    if name == "final":  # later passes override earlier ones for re-researched apps
        merged = {}
        for p in ("pass1", "pass2", "pass3", "pass4"):
            merged.update(load_pass(p))
        return merged
    d = ROOT / "results" / name
    if not d.exists():
        return {}
    return {int(p.stem): json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("[0-9][0-9][0-9].json"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="pass_name", default="pass1")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    global TAXONOMY_V1
    TAXONOMY_V1 = a.pass_name == "pass1"
    recs = load_pass(a.pass_name)
    guru_index()
    with ThreadPoolExecutor(a.workers) as ex:
        res = dict(ex.map(verify_app, recs.values()))
    out = {str(i): res[i] for i in sorted(res)}
    (ROOT / "results" / f"verify_{a.pass_name}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    redo = {}
    for i, c in res.items():
        hard = [x for x in c["issues"] if x[0] in ("quote_not_found", "source_disagrees", "contradiction", "missing_evidence", "low_confidence", "taxonomy_revised", "unsupported_claim")]
        if hard:
            redo[str(i)] = "\n".join(f"- [{k}] ({f}) {msg}" for k, f, msg in hard)
    (ROOT / "results" / f"redo_{a.pass_name}.json").write_text(json.dumps(redo, indent=2, ensure_ascii=False), encoding="utf-8")

    q = [x for c in res.values() for x in c["quotes"]]
    by = lambda s: sum(1 for x in q if x["status"] == s)
    print(f"{a.pass_name}: {len(res)} apps | quotes {len(q)}: verified {by('verified')}, not_found {by('not_found')}, "
          f"unreadable {by('unreadable')}, fetch_failed {by('fetch_failed')} | apps flagged for redo: {len(redo)}")
    from collections import Counter
    print("issue types:", Counter(k for c in res.values() for k, _, _ in c["issues"]))


if __name__ == "__main__":
    main()
