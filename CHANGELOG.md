# Changelog

## 0.5.0 — 2026-09-14

- Add source-labelled daily-incentive caps and a live percentage-used display.
- Add prepaid-credit purchase baselines, cumulative organization Costs, percentage consumed, and estimated remaining credit.
- Retrieve Cost history in bounded 180-day daily windows rather than assuming a one-day Cost value is a lifetime balance.

## 0.4.0 — 2026-09-14

- Correctly recognize the `incentivized-tier` value reported by the Usage API.
- Add an exact `--api-key-name` Usage filter so CLI totals can match a named Platform-dashboard key selection.
- Clarify that the daily Costs result applies to the organization, because the Costs API cannot filter by API key.

## 0.3.1 — 2026-09-14

- Document the macOS system-trust behavior used by `sync-api` on TLS-inspecting corporate networks.

## 0.3.0 — 2026-09-14

- Add an on-demand, read-only OpenAI Admin API import for daily Usage by processing tier and daily Costs.
- Display data-sharing-incentive tokens separately from paid API token usage and delayed authoritative daily costs.
- Document Admin Key setup, the precise Platform URL, local-secret handling, and the distinction from project service-account keys.

## 0.2.0 — 2026-09-14

- Add a private, on-demand terminal status dashboard.
- Store user-confirmed native Codex CLI plan and Billing-page API-credit snapshots with timestamps and source labels.
- Identify only the active Codex authentication mode, without accessing credentials.
- Keep the API daily-incentive state explicitly unknown until an authoritative import exists.

## 0.1.0 — 2026-09-14

- First standalone Codex desktop/CLI transcript estimator.
- Separates locally estimated model-token value, dashboard-reported account spend, and prepaid credit balance.
- Handles GPT-6 Astra token categories, per-request long-context pricing, duplicate snapshots, day baselines, coverage gaps, and unknown models.
- Provides an on-demand skill rather than a persistent status-bar integration.
