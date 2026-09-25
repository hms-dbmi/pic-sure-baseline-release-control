# pic-sure-baseline-release-control

`james_dev` pins the Banner development release for the Compose/TUI All-In-One.
The build spec uses the three component keys consumed by `release-control.sh`:

- `PSA`: backend monorepo, including Gateway, Operations, and PSAMA (PR #319).
- `PSF`: Banner display and management frontend (PR #760).
- `PSM`: Baseline banner tables and admin authorization migrations (PR #14).

Apply pending migrations before starting the new Operations service. Restart PSAMA
after the authorization migration to clear cached access rules. Operations needs
`LOGGING_SERVICE_URL` and the existing `LOGGING_API_KEY` to record banner actions.

These are source pins, not a deployment trigger. Existing Compose image overrides
must be updated explicitly; resolving this manifest alone does not replace them.
