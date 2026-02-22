# pyrainbird — Agent Notes (Intent + Structure + Maintainer Preferences)

This file captures a lightweight set of contribution notes for people using AI assistants (Codex/ChatGPT/etc.) when working on **pyrainbird**.

These preferences are inferred from maintainer review feedback (notably `allenporter/pyrainbird#528`) and are intended to help future PRs land with less back-and-forth.

## Project intent (what we’re building)

- Python client library for Rain Bird irrigation controllers, used by Home Assistant and other callers.
- Two broad interaction surfaces exist in the codebase:
  - **Local controller API** (LAN device, often accessed by host/IP).
  - **Cloud API** (remote service; must keep normal TLS verification intact).

## Repo structure (high-signal map)

- `pyrainbird/` — library code
  - `async_client.py` — async client/controller creation and request plumbing (local + cloud surfaces)
  - `exceptions.py` — library-specific exception types used by callers for control-flow decisions
- `tests/` — unit tests (prefer extending existing files over creating new ones)
- `examples/` — usage examples
- `script/` — developer helpers (`./script/test`, `./script/lint`, `./script/setup`)

## Maintainer preferences (from PR #528)

These are concrete patterns Allen asked for (or rejected), with “do this instead” guidance.

### API shape: keep public inputs host-only

- Prefer `host` / `ip` inputs for the public surface. Avoid requiring URL/scheme/path from callers.
- Discovery of HTTP vs HTTPS belongs inside the library factory (`create_controller`), not in Home Assistant or external apps.

**Instead of:**
- Accepting URLs in the local client constructor, or adding “URL normalization” as a public behavior.

**Do:**
- Keep host-only APIs stable; use URL/scheme internally only where already required (e.g., existing cloud hack paths).

### Security posture: avoid “security theater”; keep TLS scoped

- Do not implement flows that *appear* security-motivated but don’t improve the actual threat model.
  - Example: “try strict cert verify, then automatically retry with relaxed validation” does not prevent active MITM credential capture if relaxed is allowed anyway.
- Any TLS relaxation must be **scoped to local-device requests only**:
  - No connector/session-wide `ssl=False`.
  - Cloud API behavior must remain strict/unchanged.

**Instead of:**
- Globally disabling TLS verification via an `aiohttp` connector or shared session settings.

**Do:**
- Pass per-request `ssl=` (or equivalent) for the specific local request only.

### Exceptions: don’t peek at `__cause__`; raise library exceptions

**Instead of:**
- Inspecting nested exceptions (`__cause__`) to infer “this was a cert error”.

**Do:**
- Catch relevant transport exceptions and raise a clear library exception (e.g., `RainbirdCertificateError`) that callers can handle.

### Tests: keep them idiomatic and refactor-safe

- Prefer adding tests to existing files (e.g., `tests/test_async_client.py`) rather than creating one-off test modules.
- Avoid coupling tests to private fields/objects.

**Example (from PR feedback): “don’t poke into internal objects”**

**Instead of:**
- Asserting on or reaching into internals like `client._coder` (or `_url`, `_ssl_context`, etc.) in tests.

**Do:**
- Patch the boundary (constructor/factory) and assert arguments/behavior:
  - Patch `pyrainbird.async_client.AsyncRainbirdController.get_model_and_version` (string `mock.patch`).
  - Assert on the patched constructor/factory `call_args_list` directly.

### Keep code minimal; avoid adding guards for “never shipped” cases

**Instead of:**
- Adding runtime checks / assertions like “host must not be a URL” when the public contract already implies host-only and prior releases didn’t accept URLs.

**Do:**
- Keep the code path minimal and rely on the documented contract; remove defensive checks that introduce new failure modes without real benefit.

### Keep diffs focused; avoid drive-by churn

Maintainer review tends to go faster when diffs are narrowly scoped to the user-facing bugfix.

**Instead of:**
- Committing incidental formatting/whitespace changes in unrelated files.
- Committing lockfile changes as a side effect of running tests.

**Do:**
- If running `./script/test` updates `uv.lock` but you didn’t intend a dependency update, restore it before committing.
- Stage only files you intentionally changed for the fix.

## Practical contribution checklist (quick)

- Keep the public API host-only; do scheme probing inside `create_controller`.
- Do not weaken cloud TLS behavior.
- Scope any local TLS tweaks per-request only.
- Prefer library exceptions over transport internals (`__cause__`).
- Keep tests in existing modules; patch boundaries, don’t inspect internals; follow existing mocking style.
  - Prefer string-based `mock.patch("...")` and assert on `call_args_list`.
  - Avoid creating new test files unless there’s a strong existing precedent.

## Sources

- PR conversation + inline review: https://github.com/allenporter/pyrainbird/pull/528
