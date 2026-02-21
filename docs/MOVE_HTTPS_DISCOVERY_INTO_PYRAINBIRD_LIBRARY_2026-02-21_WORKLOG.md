# Worklog — Move HTTPS Discovery Into pyrainbird

Plan: `docs/MOVE_HTTPS_DISCOVERY_INTO_PYRAINBIRD_LIBRARY_2026-02-21.md`

## Phase 1 (pyrainbird discovery + local TLS policy) Progress Update
- Work completed:
  - Implemented `async_client.create_controller(...)` to probe HTTPS first and fall back to HTTP when the underlying failure is transport/SSL-related.
  - Added per-request SSL override support in `AsyncRainbirdClient` so HTTPS w/ self-signed certs can work without weakening other traffic.
  - Updated docs/examples to recommend `create_controller` (not `CreateController`) and kept the public input hostname-based.
  - Added unit tests covering discovery behavior and host/URL normalization.
- Tests run + results:
  - `./script/test` — pass
  - `.venv/bin/pre-commit run --all-files` — pass
- Issues / deviations:
  - `./script/lint` uses `uv run pre-commit ...` which rewrote `uv.lock` metadata on this machine; ran pre-commit directly from `.venv` to keep `uv.lock` unchanged.
- Next steps:
  - Send updated `pyrainbird` PR to upstream (`allenporter/pyrainbird`) aligned with maintainer feedback.
  - Follow-up: update HA Rain Bird integration to call `create_controller` once a `pyrainbird` release is cut.
