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

## Code base standards

These are concrete patterns used in the code base.

### Security posture: avoid “security theater”

- Do not implement flows that *appear* security-motivated but don’t improve the actual threat model.
  - Example: “try strict cert verify, then automatically retry with relaxed validation” does not prevent active MITM credential capture if relaxed is allowed anyway.
- Any TLS relaxation must be **scoped to local-device requests only**:
  - No connector/session-wide `ssl=False`.
  - Cloud API behavior must remain strict/unchanged.

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
