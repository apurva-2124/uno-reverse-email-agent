# Troubleshooting

| Symptom | What to check |
| --- | --- |
| Installer cannot find `main` or returns 404 | Use repo `apurva-2124/uno-reverse-email-agent`, ref `setup/proposal`, path `.agents/skills/uno-reverse`. Keep ref and path separate because the branch name contains a slash. |
| Skill is missing | Try the next turn, then restart Codex if needed. With a checkout, open the repository folder. Confirm the entire skill folder exists and the host has not disabled it. See [skill discovery](https://learn.chatgpt.com/docs/build-skills). |
| Installer says destination exists | Inspect the existing skill first. Back it up before replacing it; do not overwrite a customized installation blindly. |
| Two Uno Reverse entries appear | A personal installation and repository checkout may both be discovered. Choose one and disable the duplicate in your host. |
| `python3` missing or too old | Install Python 3.11+ using your platform's supported method; check `python3 --version`. The helper needs no pip packages. |
| Gmail unavailable or wrong mailbox | Connect Gmail in the same host/session that will run the skill, then verify mailbox identity. Reconnecting does not resume a paused policy. |
| Gmail works interactively but scheduled sends fail | Check the scheduled host's connector access, unattended permissions and ledger access. Keep on-demand mode if the host cannot support this. Do not bypass approval restrictions. |
| No emails are processed | Check activation, pause status, hours/timezone, caps and scope. Older mail is excluded unless backfill was approved; ambiguous mail and previously reserved brands are also excluded. |
| Nothing happens with the app closed | Local tasks need the computer on and app running. Installing the skill does not create an always-on cloud service. |
| Missing state in a scheduled run | Use the original absolute directory, outside disposable worktrees, accessible to every run. Do not initialize a replacement ledger: it loses deduplication. |
| Run is locked or delivery is unknown | Stop new sends. Verify the prior run has stopped and reconcile exact Sent evidence using the [recovery procedure](../.agents/skills/uno-reverse/references/autopilot.md#recovery-and-controls). A missing search result is not proof of failure; never clear reservations to retry. |
| BrandVault is unavailable | Continue with local approved facts. Signup and recipient invitations are optional and independent. |

For a bug report, [open an issue](https://github.com/apurva-2124/uno-reverse-email-agent/issues) with host/version, OS, Python version, skill revision, the failing step and a redacted error. Exclude mailbox contents, recipients, credentials and ledger databases. State whether the issue involves preview, installation, local state or a connected tool.
