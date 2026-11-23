"""Submission PDF (the form takes one file): an HTML brief rendered to A4 by headless Chromium.
All numbers come from docs/data.json, so the PDF and the live page cannot disagree.
Usage: python agent/make_submission.py -> submission/Pratyush_Mishra_Composio_takehome.pdf"""
import html, json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
P, V, A = D["patterns"], D["verification"], D["apps"]
acc = V["accuracy"]
c, ac, au = dict(P["verdict"]), dict(P["access"]), dict(P["auth"])
gaps_now = [g["app"] for g in P["composio_gaps"] if g["verdict"] == "build_now" and not g.get("weak")]
X = P.get("extras") or {}
gen_gaps = [g for g in gaps_now if g in X.get("generatable_build_now", [])]
LIVE = "https://pratyushmishra-2nd.github.io/composio-takehome/"
REPO = "https://github.com/PratyushMishra-2nd/composio-takehome"
e = html.escape
pct = lambda x: f"{round(x * 100)}%"
fq = V["final_quotes"]; q1 = V["pass1_quotes"]; bv = V["browser_verified"]

cats = list(dict.fromkeys(a["category"] for a in A))
rows = ""
for cat in cats:
    xs = [a for a in A if a["category"] == cat]
    n = {v: sum(1 for a in xs if a["verdict"] == v) for v in ("build_now", "build_with_caveat", "needs_outreach", "not_buildable")}
    segs = "".join(f'<span class="seg {v}" style="flex:{k}">{k}</span>' for v, k in n.items() if k)
    rows += f'<tr><td class="cat">{e(cat)}</td><td><div class="bar">{segs}</div></td></tr>'

findings = [
    (f"Easy wins: {c.get('build_now', 0)} of 100 can ship today",
     f"{c.get('build_with_caveat', 0)} more with a caveat; {c.get('needs_outreach', 0) + c.get('not_buildable', 0)} need outreach or have no usable API. An upper bound: gate errors on the sample skewed permissive."),
    ("Most common blocker: vendor review, then money",
     f"{ac.get('admin_approval', 0)} need vendor app review or hit an install cap (HubSpot, Attio: 25), {ac.get('self_serve_trial', 0) + ac.get('paid_plan', 0)} need a trial or paid plan, "
     f"{ac.get('customer_account', 0)} are customer-only, {ac.get('partner_gated', 0)} need a partnership. Every app but one has a documented API."),
    ("Friction clusters in sales-led SaaS and ad platforms",
     "Support and finance tools are often customer-only (DealCloud, Gladly, Pylon, Brex, PitchBook); ads sit behind app review (Google, Meta, LinkedIn). "
     "Dev-infra and productivity are nearly all build-now."),
    (f"Toolkits need both auth modes: {P['both']} offer OAuth2 and a key",
     f"OAuth2 in {au.get('oauth2', 0)}, OAuth-only in {P['oauth_only']}; key-only apps ({P['key_only']}) cluster in data/SEO and AI-native tools."),
    (f"{len(X['generatable_build_now'])} build-now apps publish a spec: generation candidates",
     f"{X['spec_claimed']} publish OpenAPI/GraphQL ({X['spec_confirmed']} confirmed), {X['webhooks_yes']} have webhooks for triggers, {X['sandbox_free']} a free sandbox. "
     f"AI-native tools are least ready ({X['by_category']['AI, Research and Media-native']['webhooks']}/10 webhooks)."),
    (f"For Composio: {len(P['composio_gaps'])} gaps, {len(gaps_now)} buildable now",
     f"{P['composio_listed']}/100 already have a toolkit (via Composio MCP). Quick adds: {', '.join(gaps_now)}; {len(gen_gaps)} have a spec ({', '.join(gen_gaps)})."),
]
fhtml = "".join(f'<div class="f"><div class="n">{i}</div><div><b>{e(t)}</b><p>{e(d)}</p></div></div>' for i, (t, d) in enumerate(findings, 1))

steps = [("Research workers", "Headless Claude Code per app, web search + fetch, JSON schema, quote + URL per field"),
         ("Non-LLM verifier", "Quote re-fetch, APIs.guru specs, MCP registry, consistency rules"),
         ("Re-research", "Flagged apps re-run with the exact disputes, 2 rounds"),
         ("Browser-use loop", f"Headless Chromium renders JS-heavy docs: +{bv} quotes confirmed"),
         ("Composio catalog", f"COMPOSIO_SEARCH_TOOLS per app → {len(P['composio_gaps'])}-app gap backlog", True),
         ("Approval tracker", f"{P['tracker_issues']} GitHub issues via Composio GITHUB_CREATE_AN_ISSUE", True)]
steps.append(("Corrections", f"{len(D.get('corrections', []))} recorded fixes: third-check rulings, own verdict rules, a distribution check, the hand check, named human calls"))
steps.insert(4, ("Enrichment pass", f"Webhooks, sandbox, rate limits, SDKs, spec: {X['quotes'].get('verified', 0)}/{sum(X['quotes'].values())} quotes confirmed; specs downloaded + parsed"))
shtml = "".join(f'<div class="st{" c" if len(s) > 2 else ""}"><b>{e(s[0])}</b><span>{e(s[1])}</span></div>' for s in steps)

page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 0 }}
* {{ box-sizing: border-box }}
body {{ margin: 0; font: 9.2pt/1.42 "Segoe UI", system-ui, sans-serif; color: #0b0b0b; }}
.wrap {{ padding: 5mm 14mm 6mm }}
.top {{ background: #0b0b0b; color: #f0efec; padding: 9mm 14mm 7mm; }}
.top .k {{ font-size: 8pt; letter-spacing: .08em; text-transform: uppercase; color: #9ec5f4 }}
.top h1 {{ font-size: 19pt; line-height: 1.15; margin: 2mm 0 2mm; font-weight: 700; letter-spacing: -.01em }}
.top p {{ margin: 0; color: #c3c2b7; font-size: 9.4pt; max-width: 165mm }}
.links {{ display: flex; gap: 2.5mm; margin-top: 4.5mm; flex-wrap: wrap }}
.links a {{ color: #0b0b0b; background: #fff; text-decoration: none; border-radius: 5px; padding: 1.6mm 3mm; font-weight: 600; font-size: 8.6pt }}
.links a.p {{ background: #3987e5; color: #fff }}
.tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; margin: 0 0 2mm }}
.tile {{ border: 1px solid #e1e0d9; border-radius: 7px; padding: 3mm 3.2mm; background: #fcfcfb }}
.tile .v {{ font-size: 17pt; font-weight: 700; letter-spacing: -.02em; line-height: 1.1 }}
.tile .l {{ color: #52514e; font-size: 7.8pt; line-height: 1.3; margin-top: 1mm }}
h2 {{ font-size: 10.5pt; margin: 4mm 0 2mm; letter-spacing: .01em }}
.cols {{ display: grid; grid-template-columns: 1.15fr 1fr; gap: 6mm }}
.f {{ display: grid; grid-template-columns: 6mm 1fr; gap: 2.4mm; margin-bottom: 2.4mm }}
.f .n {{ width: 5.4mm; height: 5.4mm; border-radius: 50%; background: #0b0b0b; color: #fff; font-weight: 700; font-size: 8pt; display: grid; place-items: center }}
.f b {{ font-size: 9.2pt }} .f p {{ margin: .6mm 0 0; color: #52514e; font-size: 8.4pt; line-height: 1.36 }}
table {{ width: 100%; border-collapse: collapse }}
td {{ padding: .9mm 0; vertical-align: middle }}
td.cat {{ width: 31mm; font-size: 7.8pt; color: #52514e; padding-right: 2mm }}
.bar {{ display: flex; gap: 1px; height: 4.6mm; border-radius: 3px; overflow: hidden }}
.seg {{ font-size: 7pt; font-weight: 600; display: flex; align-items: center; justify-content: center; color: #fff }}
.build_now {{ background: #0ca30c }} .build_with_caveat {{ background: #fab219; color: #0b0b0b }}
.needs_outreach {{ background: #ec835a; color: #0b0b0b }} .not_buildable {{ background: #d03b3b }}
.leg {{ display: flex; gap: 3mm; flex-wrap: wrap; font-size: 7.4pt; color: #52514e; margin-top: 1.5mm }}
.leg i {{ display: inline-block; width: 2.4mm; height: 2.4mm; border-radius: 1px; margin-right: 1mm; vertical-align: -.2mm }}
.steps {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 2.2mm }}
.st {{ border: 1px solid #e1e0d9; border-radius: 6px; padding: 2.2mm 2.6mm; background: #fcfcfb }}
.st.c {{ border: 1.5px solid #2a78d6; background: #f3f7fd }}
.st b {{ display: block; font-size: 8.4pt }} .st span {{ color: #52514e; font-size: 7.6pt; line-height: 1.32; display: block; margin-top: .5mm }}
.acc {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 2.2mm; margin-top: 2mm }}
.acc div {{ border-left: 3px solid #2a78d6; padding: .6mm 0 .6mm 2.4mm }}
.acc .v {{ font-size: 12pt; font-weight: 700 }} .acc .l {{ font-size: 7.6pt; color: #52514e; line-height: 1.3 }}
.note {{ font-size: 7.8pt; color: #52514e; line-height: 1.4; margin: 2mm 0 0 }}
.human {{ border-left: 3px solid #eb6834; padding-left: 2.6mm; margin-top: 3mm }}
.foot {{ margin-top: 3.5mm; padding-top: 2mm; border-top: 1px solid #e1e0d9; font-size: 7.4pt; color: #898781; display: flex; justify-content: space-between }}
code {{ font-family: Consolas, monospace; font-size: 7.6pt; background: #efeee9; padding: 0 1mm; border-radius: 2px }}
</style></head><body>
<div class="top">
  <div class="k">Composio · AI Product Ops Intern · take-home · Pratyush Mishra</div>
  <h1>100 apps, one agent: what it takes to turn an app into an agent toolkit</h1>
  <p>An agent pipeline researched auth, credential gates, API surface and MCP coverage for all 100 apps, citing a verbatim quote for every answer, then verified itself with non-LLM checks, a browser-use loop and a hand-checked 20-app sample, and opened the follow-up queue through Composio.</p>
  <div class="links"><a class="p" href="{LIVE}">Live case study ↗</a><a href="{REPO}">Source repo + README ↗</a><a href="{REPO}/issues">Approval tracker ({P['tracker_issues']} issues) ↗</a><a href="{LIVE}data.json">data.json for agents ↗</a></div>
</div>
<div class="wrap">
  <div class="tiles">
    <div class="tile"><div class="v">{c.get('build_now', 0)}/100</div><div class="l">can ship as a toolkit today with self-serve credentials (upper bound)</div></div>
    <div class="tile"><div class="v">{len(P['composio_gaps'])} gaps</div><div class="l">not yet in Composio's catalog; {len(gaps_now)} buildable now (checked via Composio MCP)</div></div>
    <div class="tile"><div class="v">{pct(q1['verified'] / q1['total'])} → {pct(fq['verified'] / fq['total'])}</div><div class="l">cited quotes confirmed on the source page, pass 1 → after the verification loops</div></div>
    <div class="tile"><div class="v">{pct(acc['pass1']['overall'])} → {pct(acc['final']['overall'])}</div><div class="l">field accuracy on a hand-checked 20-app sample: flat overall; auth {pct(acc['pass1']['field_accuracy']['auth'])} → {pct(acc['final']['field_accuracy']['auth'])}, gate field stuck at {pct(acc['final']['field_accuracy']['access'])}</div></div>
  </div>
  <div class="cols">
    <div><h2>The patterns</h2>{fhtml}</div>
    <div><h2>Verdict by category</h2><table>{rows}</table>
      <div class="leg"><span><i class="build_now"></i>build now</span><span><i class="build_with_caveat"></i>with caveat</span><span><i class="needs_outreach"></i>needs outreach</span><span><i class="not_buildable"></i>not buildable</span></div>
      <h2 style="margin-top:4.5mm">Verification, honestly</h2>
      <div class="acc">
        <div><div class="v">{fq['verified']}/{fq['total']}</div><div class="l">quotes found on the page; {V['support']['supports'] + V['support']['partial']} at least partly support their claim</div></div>
        <div><div class="v">{len(D.get('corrections', []))}</div><div class="l">corrections applied after verification, each listed with its source (accuracy measured before them)</div></div>
        <div><div class="v">{pct(V['experiment_gate_audit']['overall'])}</div><div class="l">a gate-audit loop that hurt accuracy: rolled back, kept as an experiment</div></div>
      </div>
      <p class="note">Gate classification (trial vs paid vs app review) is the hardest field. Official MCP: {P['mcp_official']} claimed, {P['mcp_official_confirmed']} independently confirmed. Every miss and correction is listed on the live page.</p>
    </div>
  </div>
  <h2>The agent</h2>
  <div class="steps">{shtml}</div>
  <div class="human note"><b style="color:#0b0b0b">Where a human was needed:</b> defining the gate taxonomy (a <i>customer-only</i> gate was split out after pass 1), choosing which loops to keep, hand-checking the 20-app reference set against vendor docs (2 labels changed, 13 notes updated; the hand check is final for those apps), and one OAuth click to connect GitHub to Composio. The agent never emails or contacts vendors on its own.</div>
  <div class="foot"><span>Run one app: <code>python agent/research.py --pass try --ids 61</code> · full pipeline in the README</span><span>Data generated {e(D['generated'])}</span></div>
</div></body></html>"""

out_dir = ROOT / "submission"; out_dir.mkdir(exist_ok=True)
(out_dir / "submission.html").write_text(page, encoding="utf-8")
pdf = out_dir / "Pratyush_Mishra_Composio_takehome.pdf"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    pg.goto((out_dir / "submission.html").as_uri(), wait_until="load")
    pg.pdf(path=str(pdf), format="A4", print_background=True, prefer_css_page_size=True, scale=0.88)
    pg.set_viewport_size({"width": 794, "height": 1123}); pg.screenshot(path=str(out_dir / "preview.png"), full_page=True)
    b.close()
print(pdf, pdf.stat().st_size, "bytes")
