# Reference-set guide (20-app sample)

The reference set in `gold.csv` was drafted blind by an independent model under these rules, then hand-checked by the author against the vendor docs (see `hand_check.json` for what changed).

20 apps, 2 per category, picked by `agent/sample.py` with a fixed seed (42) so the sample is reproducible and not cherry-picked.

`data/gold.csv` was filled **blind** from the vendors' own docs, without opening `results/`.

| Column | Allowed values |
|---|---|
| auth_methods | `;`-separated: `oauth2`, `api_key`, `basic`, `bearer_token`, `jwt`, `hmac_signature`, `session_login`, `none`, `other` |
| access | `self_serve_free` (anyone signs up, gets keys free) · `self_serve_trial` (only via time-limited trial) · `paid_plan` (public signup, but API needs a paid tier) · `admin_approval` (you can build, but vendor must review/verify the app or grant a dev token before others can connect) · `customer_account` (no public signup or dev sandbox; creds only inside an existing, usually sales-led, customer account) · `partner_gated` (partnership / contact sales / application) · `no_public_api` |
| mcp_exists | `yes` / `no`: any MCP server, official or credible community |
| mcp_official | `yes` / `no`: published by the vendor itself |
| verdict | `build_now` · `build_with_caveat` · `needs_outreach` · `not_buildable` |
| source_urls | docs pages you used, `;`-separated |
| notes | anything ambiguous |

Rule for `access`: pick the **most restrictive gate** a developer hits before a toolkit can be used by end users. Example: Google Ads = needs a developer token approved by Google → `admin_approval`.

Then run `python agent/score.py` to compare pass 1 and the final pass against this gold set.

Verdict rule: `customer_account` or `partner_gated` with no free developer sandbox → `needs_outreach`.
