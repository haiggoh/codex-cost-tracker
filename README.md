# Codex Cost Tracker

Version 0.2.0. On-demand, read-only **model-token value estimates** for local Codex desktop and CLI transcripts, plus private snapshots of distinct ChatGPT/Codex plan and API-credit pools. It never merges their budgets.

## Use

Requires Python 3.9+; no packages, credentials, background process, or network access.

```sh
python3 scripts/report.py --help
python3 scripts/report.py --timezone Europe/Berlin
python3 scripts/report.py --session TASK_ID --tier standard --json
python3 scripts/report.py --all-time
python3 scripts/report.py --account-spend-usd 8.29 --account-window "last 7 days"
python3 scripts/status.py status
python3 scripts/status.py snapshot-plan --remaining-percent 61 --reset-at '2026-10-14T16:00:00+00:00'
python3 scripts/status.py snapshot-api-credit --usd 50
```

The default reads today's records in UTC. Set `--timezone` to use a different day boundary. `CODEX_HOME` or `--home` selects the Codex data directory; default `~/.codex`. Both `sessions` and `archived_sessions` are scanned. Desktop and CLI use the same reader when they share this data directory. Source client is shown in JSON. The actual desktop records have been exercised; CLI compatibility is based on the shared transcript format and still requires a real CLI session check.

## What the numbers mean

- **Standard/Fast USD:** alternative list-price values of the recorded model tokens, not confirmed charges. `--tier auto` uses a recorded service tier only when available. `--tier standard` or `--tier fast` explicitly selects an assumption.
- **Actual charged USD:** unknown from local files. Add the amount you read from the OpenAI Usage dashboard with `--account-spend-usd` and its exact filter with `--account-window`; it is retained as a separate, user-reported account total rather than being merged with a local estimate.
- **Remaining API account budget:** unknown. An optional `--budget-usd` is a user-supplied reporting cap for the selected period, not a fetched balance. It is never inferred from Claude/Joyia settings. Remaining cap is withheld when usage coverage or tier is incomplete.
- **Coverage:** local transcripts only. Separately billed tools, taxes, requests from other programs/devices, and missing records are excluded. Total-only imported histories are unpriced, not free. Other models are explicitly unpriced in this first version.

GPT-6 Astra pricing was verified on 2026-09-14: Standard per million tokens is $10 ordinary input, $1 cached input, $12.50 cache writes, $50 output. Requests over 272,000 input tokens use 2x input/cache and 1.5x output rates; Fast doubles applicable rates. Cached and cache-write tokens are subsets of input; reasoning is a subset of output and is not added again. Rates are a dated snapshot; historical repricing is not supported.

Sources: [model pricing](https://developers.openai.com/api/docs/models/gpt-6-astra), [cache accounting](https://developers.openai.com/api/docs/guides/prompt-caching), [prepaid billing](https://help.openai.com/en/articles/8264644-how-can-i-set-up-prepaid-billing), [complimentary-token eligibility](https://help.openai.com/en/articles/10306912-sharing-feedback-evals-and-api-data-with-openai).

`scripts/status.py` reads only the `auth_mode` label from `~/.codex/auth.json`; it never reads or displays a key or ChatGPT token. Its state file defaults to `$XDG_STATE_HOME/codex-cost-tracker/status.json` (or `~/.local/state/...`) and is mode 0600. Record a native CLI `/status` percentage with `snapshot-plan`; it is a timestamped snapshot, not a continuous monitor. The daily incentive row remains unknown until a future authoritative Usage API import is added.

The reader ignores duplicate cumulative snapshots, uses prior records to establish day baselines, prices each known response separately, and flags counter resets/gaps rather than inventing missing cost. No hook, scheduler, marketplace, or existing plugin is changed.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 scripts/report.py --help
```
