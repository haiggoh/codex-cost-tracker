# Codex Cost Tracker

Version 0.3.0. On-demand, read-only **model-token value estimates** for local Codex desktop and CLI transcripts, plus private snapshots and authoritative daily API usage for distinct ChatGPT/Codex plan and API-credit pools. It never merges their budgets.

## Use

Requires Python 3.9+ and the macOS system `curl`; no packages or background process. Local transcript reports use no network access. `sync-api` makes two read-only OpenAI Admin API requests.

```sh
python3 scripts/report.py --help
python3 scripts/report.py --timezone Europe/Berlin
python3 scripts/report.py --session TASK_ID --tier standard --json
python3 scripts/report.py --all-time
python3 scripts/report.py --account-spend-usd 8.29 --account-window "last 7 days"
python3 scripts/status.py status
python3 scripts/status.py snapshot-plan --remaining-percent 61 --reset-at '2026-10-14T16:00:00+00:00'
python3 scripts/status.py snapshot-api-credit --usd 50
python3 scripts/status.py sync-api --key-file ~/.api_keys/gpt-account-service
```

The default reads today's records in UTC. Set `--timezone` to use a different day boundary. `CODEX_HOME` or `--home` selects the Codex data directory; default `~/.codex`. Both `sessions` and `archived_sessions` are scanned. Desktop and CLI use the same reader when they share this data directory. Source client is shown in JSON. The actual desktop records have been exercised; CLI compatibility is based on the shared transcript format and still requires a real CLI session check.

## What the numbers mean

- **Standard/Fast USD:** alternative list-price values of the recorded model tokens, not confirmed charges. `--tier auto` uses a recorded service tier only when available. `--tier standard` or `--tier fast` explicitly selects an assumption.
- **Actual charged USD:** unknown from local files. Add the amount you read from the OpenAI Usage dashboard with `--account-spend-usd` and its exact filter with `--account-window`; it is retained as a separate, user-reported account total rather than being merged with a local estimate.
- **Remaining API account budget:** unknown. An optional `--budget-usd` is a user-supplied reporting cap for the selected period, not a fetched balance. It is never inferred from Claude/Joyia settings. Remaining cap is withheld when usage coverage or tier is incomplete.
- **Coverage:** local transcripts only. Separately billed tools, taxes, requests from other programs/devices, and missing records are excluded. Total-only imported histories are unpriced, not free. Other models are explicitly unpriced in this first version.

GPT-6 Astra pricing was verified on 2026-09-14: Standard per million tokens is $10 ordinary input, $1 cached input, $12.50 cache writes, $50 output. Requests over 272,000 input tokens use 2x input/cache and 1.5x output rates; Fast doubles applicable rates. Cached and cache-write tokens are subsets of input; reasoning is a subset of output and is not added again. Rates are a dated snapshot; historical repricing is not supported.

Sources: [model pricing](https://developers.openai.com/api/docs/models/gpt-6-astra), [cache accounting](https://developers.openai.com/api/docs/guides/prompt-caching), [prepaid billing](https://help.openai.com/en/articles/8264644-how-can-i-set-up-prepaid-billing), [complimentary-token eligibility](https://help.openai.com/en/articles/10306912-sharing-feedback-evals-and-api-data-with-openai).

`scripts/status.py` reads only the `auth_mode` label from `~/.codex/auth.json`; it never reads or displays a key or ChatGPT token. Its state file defaults to `$XDG_STATE_HOME/codex-cost-tracker/status.json` (or `~/.local/state/...`) and is mode 0600. Record a native CLI `/status` percentage with `snapshot-plan`; it is a timestamped snapshot, not a continuous monitor.

## Read daily API usage and the free incentive

`sync-api` reads the OpenAI organization Usage API grouped by processing tier and model, then reads the matching daily Costs API total. The status display separately shows:

- **Daily API incentive:** input/output tokens and requests served on a data-sharing incentive tier.
- **Paid API usage today:** input/output tokens and requests served on every other processing tier.
- **Authoritative API Costs:** the API Costs total for the same UTC day. This can lag usage and is not the same thing as a prepaid-credit balance.

The command stores only those aggregates, their UTC day, and an observation timestamp. It does not store API responses, project IDs, model rows, the key, or its redacted form. A missing incentive row means zero eligible activity reported for that day; an unavailable request remains `unknown` and is never reported as zero.

The organization endpoints require an **Admin API key**, created by an Organization Owner at [Platform → Organization → Admin Keys](https://platform.openai.com/settings/organization/admin-keys). An ordinary project API key—including one created through the **Service account** tab at [Platform → API keys](https://platform.openai.com/api-keys)—can call models but does not have this organization Usage/Costs access. A 403 from `sync-api` therefore means use an Admin Key, not that the tracker found zero usage.

Create the Admin Key in the Platform UI, place its bare value in a private local file, and retain mode `0600`:

```sh
chmod 600 ~/.api_keys/gpt-account-service
python3 scripts/status.py sync-api --key-file ~/.api_keys/gpt-account-service
python3 scripts/status.py status
```

Use `--date YYYY-MM-DD` to query an earlier UTC day. The account must already be opted into the data-sharing program for eligible API traffic to receive complimentary tokens; this tracker reads usage only and never changes account data controls.

The reader ignores duplicate cumulative snapshots, uses prior records to establish day baselines, prices each known response separately, and flags counter resets/gaps rather than inventing missing cost. No hook, scheduler, marketplace, or existing plugin is changed.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 scripts/report.py --help
```
