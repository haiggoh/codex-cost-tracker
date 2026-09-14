---
name: codex-cost
description: Report Codex desktop and CLI token-value estimates from native local session records, separately from confirmed API charges and account credits.
---

# Codex Cost

Run the bundled `../../scripts/report.py` with Python 3. Start with `--help` if arguments are unclear. Use the actual current task ID with `--session` for task cost; omit it for all local sessions. Use `--timezone Europe/Berlin` only when that is the user's requested/local timezone, otherwise use the appropriate IANA timezone. JSON output includes coverage details.

Report the snapshot timestamp, model-token estimate, processing-tier evidence/assumption, and missing coverage. Default to `--tier auto`; do not silently assume a tier. Unknown models, total-only imports, and missing data are unpriced, never zero cost.

Do not call estimates actual spend or subtract them from the user's purchased balance. When the user supplies a dashboard value, pass `--account-spend-usd` together with the exact dashboard filter as `--account-window`; report it separately from local token estimates. Billing adjustments and complimentary allowances require account evidence. An unchanged credit balance alone does not prove free usage. Never inherit Claude Code/Joyia budgets, markup, ledger values, or authentication assumptions. Never modify privacy/data-sharing settings to gain free tokens.

The first version prices GPT-6 Astra only using the documented dated rates. It reads local files without network calls or credentials. Explain that account billing and remaining credit are unknown unless separately verified, and that tool fees and usage from other devices/programs are outside the estimate. Do not claim a published or installed plugin solely because this source package exists.
