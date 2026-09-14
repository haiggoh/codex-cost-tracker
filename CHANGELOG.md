# Changelog

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
