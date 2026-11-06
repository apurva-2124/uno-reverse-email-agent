# Contributing

Open an issue for a bug or proposed workflow change, or submit a focused pull request against `main`.

## Structure

The installable package is `.agents/skills/uno-reverse/`. `SKILL.md` is the entrypoint; `references/` holds supporting workflow details; `scripts/ledger.py` manages local state; `agents/openai.yaml` provides Codex discovery metadata. Keep the package self-contained and resolve helper paths relative to it.

Repository-level user guides live in `docs/`; helper tests live in `tests/`. There is no build step or third-party Python runtime dependency. Use Python 3.11 or later.

## Validation

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 .agents/skills/uno-reverse/scripts/ledger.py --help
git diff --check
```

For workflow changes, review the scenarios in [evaluation.md](.agents/skills/uno-reverse/references/evaluation.md). Describe what you tested and distinguish synthetic checks from live connector validation. Tests must not send mail, connect accounts or start schedules. Add meaningful tests when changing helper behavior.

Keep credentials, email contents, recipient details and runtime ledgers out of Git and issue reports. Preserve explicit policy activation, durable deduplication and pause-on-unknown behavior. Optional BrandVault setup and recipient invitations remain independent choices.

Contributions are distributed under the repository's [MIT license](LICENSE).
