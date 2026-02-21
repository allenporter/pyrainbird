---
title: "pyrainbird — Auto-detect Local HTTP/HTTPS — Architecture Plan"
date: 2026-02-21
status: active
fallback_policy: forbidden
owners: [Blake Messer]
reviewers: [Allen Porter]
doc_type: architectural_change
related:
  - https://github.com/allenporter/pyrainbird/pull/528
  - https://github.com/home-assistant/core/issues/120678
  - https://github.com/home-assistant/core/issues/154843
  - https://github.com/home-assistant/core/issues/162671
  - https://github.com/home-assistant/core/pull/163333
  - https://github.com/rblakemesser/ha-core/pull/1
---

# TL;DR

- Worklog: `docs/MOVE_HTTPS_DISCOVERY_INTO_PYRAINBIRD_LIBRARY_2026-02-21_WORKLOG.md`
- **Outcome:** Home Assistant’s Rain Bird integration connects to both old (HTTP) and updated (HTTPS/self-signed) controllers without any user-facing config changes.
- **Problem:** Updated Rain Bird controller firmware appears to require HTTPS on the local `/stick` endpoint (often with a self-signed cert), while current clients assume HTTP and/or can’t safely handle that TLS setup.
- **Approach:** Move protocol discovery + local TLS handling into `pyrainbird` (not Home Assistant) via a new async factory (`create_controller`) that probes HTTPS→HTTP and returns a ready controller, while keeping the async client constructor “hostname-first”.
- **Plan:** Add `create_controller` + local SSL policy in `pyrainbird` → update HA Rain Bird integration to call it → cut a `pyrainbird` release → bump HA dependency → follow-up cleanup (tests/docs, remove URL hacks where possible).
- **Non-negotiables:**
  - No user-facing config flow changes (users still enter host/IP + PIN/password).
  - Protocol discovery happens in `pyrainbird`, not HA.
  - TLS verification is **not** globally disabled; if we relax cert checks, it is **local-controller-only**.
  - Fail loudly if neither HTTPS nor HTTP works (no silent “kind of works” mode).
  - Backwards compatible with older controllers that only speak HTTP.
  - Minimal, testable API surface change (one new factory; avoid leaking URL semantics to callers).

---

<!-- arch_skill:block:planning_passes:start -->
<!--
arch_skill:planning_passes
deep_dive_pass_1: not started
external_research_grounding: not started
deep_dive_pass_2: done 2026-02-21
recommended_flow: deep dive -> external research grounding -> deep dive again -> phase plan -> implement
note: This is a warn-first checklist only. It should not hard-block execution.
-->
<!-- arch_skill:block:planning_passes:end -->

---

# 0) Holistic North Star

## 0.1 The claim (falsifiable)
> If `pyrainbird` owns protocol discovery for the local controller API (HTTPS vs HTTP) and applies a local-only TLS policy that supports updated controllers (including common self-signed certs), then Home Assistant users can set up and run the Rain Bird integration by entering only host/IP + PIN/password (unchanged UX), and both updated and legacy controllers successfully complete config flow and normal polling/commands.

## 0.2 In scope
- UX surfaces (what users will see change):
  - Home Assistant Rain Bird config flow remains “host/IP + password/PIN”.
  - Setup succeeds for controllers updated by the Rain Bird 2.x app/firmware (no more “Failed to connect / Error communicating…” when the only issue is HTTPS/TLS).
- Technical scope (what code will change):
  - `pyrainbird`: add an async controller factory (e.g., `async def create_controller(...)`) that:
    - probes `https://<host>/stick` then `http://<host>/stick` (or a stricter decision rule),
    - chooses the correct `aiohttp` SSL behavior for *local* requests,
    - returns an `AsyncRainbirdController` ready for use.
  - `home-assistant/core`: update the Rain Bird integration to call the new `pyrainbird` factory rather than doing scheme/TLS discovery itself.

## 0.3 Out of scope
- UX surfaces (what users must NOT see change):
  - No new “scheme” field, no “try HTTPS” toggle, no user prompt about certificates.
  - No requirement for users to type `https://...`.
- Technical scope (explicit exclusions):
  - Do not relax TLS verification for Rain Bird cloud APIs (cloud must remain properly verified).
  - Do not introduce long-lived runtime shims outside of the explicit discovery step.
  - Do not broaden scope to unrelated Rain Bird protocol changes unless they are required to make HTTPS local connectivity work.

## 0.4 Definition of done (acceptance evidence)
- Home Assistant config flow succeeds against:
  - a controller that only accepts HTTPS to `/stick` (with a self-signed cert), and
  - a controller that accepts HTTP to `/stick` (legacy behavior).
- The integration’s steady-state operations (model/version fetch, schedule/coordinator refresh) work after setup on both classes of device.
- Evidence plan (common-sense; non-blocking):
  - Primary signal (keep it minimal; prefer existing tests/checks): `pyrainbird` unit tests with mocked `aiohttp` responses that prove scheme selection + local SSL policy is applied only to local endpoints.
  - Optional second signal (only if needed): HA integration tests for config flow + setup entry using `AiohttpClientMocker` to ensure HA calls the factory and does not require URL input.

## 0.5 Key invariants (fix immediately if violated)
- Local-vs-cloud TLS policy must be explicit and scoped (no “disable SSL verify globally”).
- Home Assistant should not need to encode URL semantics (host remains host in user input).
- Fail-loud boundary: if both HTTPS and HTTP fail, surface a clear connection error (not a silent downgrade).
- Fallback policy (strict):
  - Default: **NO fallbacks or runtime shims** (feature must work correctly or fail loudly).
  - Note: the only “dual path” tolerated is the one-time protocol discovery probe; steady-state should use a single chosen transport.

---

# 1) Key Design Considerations (what matters most)

## 1.1 Priorities (ranked)
1) Restore connectivity for updated controllers without user-visible change.
2) Keep backwards compatibility for legacy controllers.
3) Keep TLS semantics safe: local-only relaxation (if needed), cloud unchanged.

## 1.2 Constraints
- Correctness: protocol choice must be reliable (avoid “works once, then flakes”).
- Performance: discovery should be fast; avoid repeated retries during normal polling.
- Offline / latency: local calls should remain local; keep timeouts bounded.
- Compatibility / migration (default: hard cutover; no shims): support both firmwares via deterministic discovery and then a single chosen path.
- Operational / observability: log enough to diagnose scheme/TLS selection without leaking secrets.

## 1.3 Architectural principles (rules we will enforce)
- Library owns discovery; HA is a consumer of a stable, hostname-based API.
- Fail-loud boundaries with actionable error reporting.
- Separate concerns: local API transport vs cloud API transport.

## 1.4 Known tradeoffs (explicit)
- Probing adds a small setup cost (one extra request in the common case) → acceptable to avoid user config changes.
- Allowing self-signed TLS (local-only) increases MITM risk on LAN → acceptable given local device control model, but must remain scoped and explicit.

---

# 2) Problem Statement (existing architecture + why change)

## 2.1 What exists today
- `pyrainbird` async client/controller used by Home Assistant’s Rain Bird integration.
- HA config flow collects host + password and performs test calls; HA then sets up polling via coordinator.
- Current assumptions bake in an HTTP base URL for the local `/stick` endpoint (or rely on caller-provided URL as a workaround).

## 2.2 What’s broken / missing (concrete)
- Symptoms:
  - Config flow fails with “Failed to connect / Error communicating with Rain Bird device”.
  - Rain Bird mobile app continues to control the device after controller update.
- Root causes (hypotheses):
  - Updated controllers require HTTPS for local API and/or reject plain HTTP.
  - Updated controllers may present self-signed TLS certificates, which default TLS verification rejects.
- Why now:
  - New Rain Bird 2.x app + firmware updates appear to shift local API behavior.

## 2.3 Constraints implied by the problem
- Must support both protocol modes in the field (legacy HTTP and new HTTPS).
- Must not require end-user knowledge of URL schemes/certificates.

---

<!-- arch_skill:block:research_grounding:start -->
# Research Grounding (external + internal “ground truth”)

## External anchors (papers, systems, prior art)
- `aiohttp` client SSL controls (`ClientSession.request(..., ssl=...)` and `TCPConnector(ssl=...)`) — **adopt** per-request (or per-client) SSL configuration so any certificate relaxation is scoped to local requests only (no accidental cloud weakening).
- Python `ssl.SSLContext` defaults (`ssl.create_default_context()`, `check_hostname`, `verify_mode`) — **adopt** explicit SSLContext construction when we must tolerate self-signed local TLS; **reject** global “disable SSL verification” defaults that could leak beyond local transport.
- Home Assistant integration conventions (`async_create_clientsession`, config-flow timeouts, error mapping) — **adopt** HA’s timeout/fail-loud behavior; **reject** pushing scheme/cert UX into HA config flow (library owns discovery).

## Internal ground truth (code as spec)
- Authoritative behavior anchors (do not reinvent):
  - `pyrainbird/async_client.py` — `AsyncRainbirdClient.request()` exception mapping (`403`→`RainbirdAuthException`, `503`→`RainbirdDeviceBusyException`, transport→`RainbirdApiException`); `CreateController()` wiring (local + `CLOUD_API_URL` cloud client); `AsyncRainbirdController.get_model_and_version()` cache + retry enabling.
  - `pyrainbird/encryption.py` — `PayloadCoder` behavior (password `None` ⇒ plaintext for cloud) and controller error mapping to `RainbirdApiException`.
  - `tests/conftest.py` — fixtures pass *paths* (`"/stick"`, `"/phone-api"`) as the “host” to `AsyncRainbirdClient`; this path-based behavior is relied on by tests and must remain compatible.
  - `tests/test_async_client.py` — contracts for fail-loud errors + device-busy retries (what is retried, what is not).
  - `examples/mitm_rainbird.py` — reference implementation for decoding `/stick` traffic via mitmproxy (useful for validating what the mobile app is doing on updated firmware).
  - (HA core) `homeassistant/components/rainbird/config_flow.py` — `_test_connection()` currently constructs `AsyncRainbirdClient(session, host, password)` and calls `get_serial_number()` + `get_wifi_params()` under a timeout, mapping exceptions to `timeout_connect` / `invalid_auth` / `cannot_connect`.
  - (HA core) `homeassistant/components/rainbird/__init__.py` — `async_setup_entry()` constructs the controller and calls `get_model_and_version()` (auth failures become `ConfigEntryAuthFailed`; other API failures become `ConfigEntryNotReady`).
- Existing patterns to reuse:
  - `AsyncRainbirdController.get_model_and_version()` as “probe + cache + retry configuration” — ideal for discovery so we don’t pay extra requests after a successful probe.
  - Local vs cloud client split (`local_client` vs `cloud_client`) — preserve this boundary so local TLS relaxation can’t affect cloud calls.
  - Test harness uses an aiohttp app with `/stick` — extend by mocking `ClientSession.request` to raise representative `aiohttp` SSL/connection exceptions for discovery decision logic.

## Open questions (evidence-based)
- What is the smallest reliable probe for scheme selection (and error taxonomy)? — Evidence: affected-device logs that preserve the underlying `aiohttp` exception type (cert verify error vs connect refused vs auth).
- Do updated controllers hard-fail HTTP, or redirect it? — Evidence: `curl -v http://<host>/stick` vs `curl -vk https://<host>/stick` (status codes + handshake behavior).
- For HTTPS local, is the only blocker certificate verification? — Evidence: classify observed `aiohttp` client exceptions from a failing HA setup attempt.
- What probe order minimizes risk/time? (e.g., HTTPS verify → HTTPS relaxed → HTTP) — Evidence: one updated controller trace + one legacy trace, verifying the order doesn’t regress legacy.
- Should the chosen scheme be persisted anywhere (library cache vs HA config entry), or be re-discovered on startup? — Evidence: whether controllers can flip modes without explicit firmware/app action.
<!-- arch_skill:block:research_grounding:end -->

---

<!-- arch_skill:block:current_architecture:start -->
# 4) Current Architecture (as-is)

## 4.1 On-disk structure
```text
pyrainbird/
  async_client.py           # AsyncRainbirdClient + AsyncRainbirdController + CreateController
  encryption.py             # PayloadCoder (encode/decode) + controller error surfacing
  exceptions.py             # RainbirdApiException/RainbirdAuthException/... (type taxonomy)
examples/
  rainbird_tool.py          # CLI calls CreateController (library public surface)
  mitm_rainbird.py          # /stick decode helper (ground truth for stick traffic)
tests/
  conftest.py               # aiohttp app exposes /stick + /phone-api; path-style host fixture
  test_async_client.py      # request/response + failure mapping + retry behavior
  test_url_normalization.py # local endpoint URL normalization contract

(home-assistant/core) homeassistant/components/rainbird/
  coordinator.py            # async_create_clientsession (TCPConnector limit=1) + poll loops
  config_flow.py            # _test_connection constructs AsyncRainbirdClient(host, password)
  __init__.py               # async_setup_entry constructs AsyncRainbirdClient(host, password)
```

## 4.2 Control paths (runtime)
* Flow A — Local `/stick` RPC (library)
  * `AsyncRainbirdController.<op>()` → `AsyncRainbirdClient.request()` → `PayloadCoder.encode_command()` (encrypted JSON-RPC for local) → `aiohttp.ClientSession.request("post", <endpoint>)` → `PayloadCoder.decode_command()` → typed dataclass response (or exception)
* Flow B — Controller “probe + cache + retry config” (library)
  * `AsyncRainbirdController.get_model_and_version()` caches the response and may swap in a retrying client (`with_retry_options(_device_busy_retry())`) when model metadata indicates the device benefits from retries.
* Flow C — HA config flow test connection
  * `RainbirdConfigFlowHandler._test_connection()` creates a short-lived `ClientSession` via `coordinator.async_create_clientsession()` → constructs `AsyncRainbirdController(AsyncRainbirdClient(session, host, password))` → calls `get_serial_number()` + `get_wifi_params()` under a timeout → maps exceptions to HA error codes → closes session.
* Flow D — HA steady-state polling
  * `async_setup_entry()` creates a shared session → constructs controller → calls `get_model_and_version()` (gates setup, classifies auth vs not-ready) → `RainbirdUpdateCoordinator` runs serial local calls under a timeout (device can only handle one in-flight request).

## 4.3 Object model + key abstractions
* Key types:
  * `pyrainbird.async_client.AsyncRainbirdClient` — transport + JSON-RPC + encryption; owns endpoint URL construction and error mapping.
  * `pyrainbird.async_client.AsyncRainbirdController` — device operations; owns caching and per-model retry enabling.
  * `pyrainbird.encryption.PayloadCoder` — local encryption/decryption and controller “error” decoding.
  * `pyrainbird.exceptions.RainbirdApiException` (+ subclasses) — user-facing exception taxonomy.
* Ownership boundaries:
  * `pyrainbird` owns transport details (endpoint path `/stick`, payload format, encryption).
  * Home Assistant owns UX + lifecycle (config flow, config entry setup, polling cadence, timeouts).
* Public APIs (relevant here):
  * `CreateController(websession, host, password) -> AsyncRainbirdController` (sync factory).
  * `AsyncRainbirdClient(websession, host, password)` (internal-ish; used directly by HA and tests today).

## 4.4 Observability + failure behavior today
* Logs:
  * `pyrainbird.encryption.PayloadCoder` logs JSON-RPC request/response bodies at debug.
  * `pyrainbird.async_client.AsyncRainbirdClient` logs endpoint selection and transport errors at debug.
* Failure surfaces:
  * HTTP `403` becomes `RainbirdAuthException`.
  * HTTP `503` becomes `RainbirdDeviceBusyException` (a `RainbirdApiException` subtype).
  * Transport/TLS failures are raised as `RainbirdApiException("Error communicating…")` with the underlying `aiohttp` exception preserved as `__cause__` for callers that need to classify it.
* Common failure modes (as reported in linked HA issues):
  * Local controllers updated by Rain Bird 2.x firmware appear to reject HTTP and/or require HTTPS with a self-signed certificate → current HA call sites fail early during config flow/setup.
<!-- arch_skill:block:current_architecture:end -->

---

<!-- arch_skill:block:target_architecture:start -->
# 5) Target Architecture (to-be)

## 5.1 On-disk structure (future)
```text
pyrainbird/
  async_client.py          # add async factory + local TLS policy plumbing
  (optional) discovery.py  # only if factory grows beyond “a few screens”

(home-assistant/core) homeassistant/components/rainbird/
  config_flow.py           # calls pyrainbird async factory; keeps UX unchanged
  __init__.py              # calls pyrainbird async factory; keeps entry title unchanged
```

## 5.2 Control paths (future)
* Flow A (new) — Library-owned local transport discovery
  * `create_controller(session, host, password)`:
    * preserves user UX by accepting a plain hostname/IP (no scheme required),
    * probes local connectivity in a deterministic order (default: HTTPS → HTTPS (local-only relaxed cert) → HTTP),
    * continues to the next candidate **only** for “wrong transport” failures (connection refused / TLS handshake mismatch / certificate verify error when switching to relaxed).
  * On first successful probe, returns an `AsyncRainbirdController` configured to use that local transport going forward.
* Flow B (new) — HA config flow and setup entry become “dumb callers”
  * HA still collects `CONF_HOST` + `CONF_PASSWORD` and keeps the entry title as the user-entered host.
  * HA replaces direct `AsyncRainbirdClient(...)` construction with `await pyrainbird.async_client.create_controller(...)` and continues calling the same controller ops (`get_serial_number`, `get_wifi_params`, `get_model_and_version`).

## 5.3 Object model + abstractions (future)
* New/changed surface:
  * `async def create_controller(websession, host, password, *, timeout=...) -> AsyncRainbirdController`
    * Host stays host (no URL required by callers).
    * Factory owns scheme selection and local-only TLS handling.
* Internal contracts:
  * Local TLS policy is applied per-local-request/per-local-client (e.g., `aiohttp` `ssl=` kwarg), never by mutating the shared session connector in a way that could affect other traffic.
  * If `host` is already a “path host” (e.g., `"/stick"`, used by tests/fixtures), discovery is bypassed and the path is used directly.
  * If `host` is an explicit URL, treat it as an advanced override (no probing), but still allow local-only cert relaxation when it’s `https://`.

## 5.4 Invariants and boundaries
* Fail-loud boundaries:
  * If discovery cannot establish a working local transport, fail with an actionable exception (include scheme attempts + last failure class; do not leak secrets).
* Single source of truth:
  * `pyrainbird` is the SSOT for local transport selection; HA does not grow its own scheme/TLS heuristics.
* UX invariants:
  * HA config entry title and user input remain “host/IP” (no `https://` visible in the UI unless the user explicitly typed it).
* Security invariants:
  * Cloud API requests (if used by non-HA consumers) must retain certificate verification; any relaxation is local-controller-only.
<!-- arch_skill:block:target_architecture:end -->

---

<!-- arch_skill:block:call_site_audit:start -->
# 6) Call-Site Audit (exhaustive change inventory)

## 6.1 Change map (table)

| Area | File | Symbol / Call site | Current behavior | Required change | Why | New API / contract | Tests impacted |
| ---- | ---- | ------------------ | ---------------- | --------------- | --- | ------------------ | -------------- |
| Library API | `pyrainbird/async_client.py` | `CreateController(...)` | Sync factory builds `AsyncRainbirdClient(host, ...)` + cloud client and returns controller. | Add `async def create_controller(...)` and treat `CreateController` as legacy (keep, deprecate, or re-point if safe). | HA and updated firmware need async probing; we can’t do discovery reliably in a sync factory. | `create_controller(session, host, password) -> AsyncRainbirdController` | Add new unit tests for probe ordering + error taxonomy. |
| Local endpoint | `pyrainbird/async_client.py` | `AsyncRainbirdClient.__init__` | Builds `_url` from `host` (supports path hosts; supports URL-ish inputs). | Keep path-host support (tests), but refactor internals so host remains host while scheme/ssl are explicit (avoid “caller must pass URL”). | Align with upstream maintainer preference; avoid leaking URL semantics to HA/config UX. | Internal representation: `{host, scheme, path='/stick', ssl_policy}` | `tests/conftest.py`, `tests/test_url_normalization.py` may need updates depending on implementation. |
| Local TLS | `pyrainbird/async_client.py` | `AsyncRainbirdClient.request` | Calls `session.request(..., url, ...)` with no explicit SSL override. | Add optional per-request SSL override (only when configured) so self-signed local HTTPS can work without weakening other traffic. | Must not disable verification globally; local-only relaxation is the safe boundary. | `AsyncRainbirdClient(..., ssl=...)` or equivalent; `request(..., ssl=self._ssl)` | New tests needed to ensure SSL override is only applied when configured. |
| Retry clone | `pyrainbird/async_client.py` | `with_retry_options(...)` | Returns new client but currently only preserves host/password. | Ensure retry client preserves the local SSL policy and scheme settings. | Avoid discovery succeeding then losing TLS behavior after retry swap. | `with_retry_options` copies full connection config | Extend existing retry tests if needed. |
| Examples | `examples/rainbird_tool.py` | `CreateController(...)` call | CLI uses legacy sync factory. | Switch to `await create_controller(...)` (CLI is already async). | Keeps example working on updated controllers; aligns docs with new API. | Same env vars; different factory call | N/A (example). |
| Docs | `README.md` | Quickstart `CreateController(...)` | Quickstart suggests legacy factory. | Update to `await create_controller(...)` once API exists (or document both). | Prevents new users from copy/pasting broken setup on new firmware. | New recommended entrypoint | N/A (docs). |
| HA config flow | (HA core) `homeassistant/components/rainbird/config_flow.py` | `_test_connection()` | Constructs `AsyncRainbirdClient(session, host, password)` directly. | Replace with `controller = await pyrainbird.create_controller(session, host, password)` then keep existing `get_serial_number/get_wifi_params` behavior. | Keep UX unchanged and remove HA-side discovery logic. | HA calls library factory; host stays host in entry/title. | Update HA tests under `tests/components/rainbird/` to mock discovery outcomes. |
| HA setup entry | (HA core) `homeassistant/components/rainbird/__init__.py` | `async_setup_entry()` | Constructs controller directly; calls `get_model_and_version()`. | Replace construction with `await pyrainbird.create_controller(...)`; keep failure mapping. | Ensures updated controllers work on startup; centralizes discovery. | Same controller API | Update HA tests under `tests/components/rainbird/`. |
| HA sessions | (HA core) `homeassistant/components/rainbird/coordinator.py` | `async_create_clientsession()` | Creates `ClientSession(TCPConnector(limit=1))`. | No change required if library uses per-request SSL override (preferred). | Avoid changing HA session semantics; keep single in-flight constraint. | Library must not require connector-level SSL disable. | None (unless tests rely on constructor behavior). |

## 6.2 Migration notes
* Deprecated APIs (if any):
  * Consider deprecating `CreateController` in favor of `create_controller` for async callers; keep it for backwards compatibility but document it may not work on HTTPS-only firmware.
* Delete list (what must be removed; include legacy shims/parallel paths if any):
  * Delete/avoid HA-side scheme probing logic (once library factory exists). No parallel discovery in HA.

## 6.3 Pattern Consolidation Sweep (anti-blinders; scoped by plan)
| Area | File / Symbol | Pattern to adopt | Why (drift prevented) | Proposed scope (include/defer/exclude) |
| ---- | ------------- | ---------------- | ---------------------- | ------------------------------------- |
| Library usage docs | `README.md` (Quickstart) | Prefer `create_controller` as the default entrypoint | Prevents “copy/paste broken” setups on new firmware | include |
| Example CLI | `examples/rainbird_tool.py:main()` | Use `create_controller` | Keeps example aligned with supported reality | include |
| HA integration | (HA core) `config_flow.py`, `__init__.py` | Always call library factory | Prevents reintroducing HA-side scheme/TLS heuristics later | include |
| Test fixtures | `tests/conftest.py` | Preserve path-host behavior | Prevents breaking existing unit tests and fixture approach | include |
| Anything cloud-related | `pyrainbird/async_client.py` cloud client | Keep default TLS verification | Prevents accidental security regression | include |
<!-- arch_skill:block:call_site_audit:end -->

---

# 7) Depth-First Phased Implementation Plan (authoritative)

> Rule: systematic build, foundational first; every phase has exit criteria + explicit verification plan (tests optional).

## Phase 1 — `pyrainbird` discovery + local TLS policy (done 2026-02-21)
- Goal: Introduce `create_controller` and prove behavior via unit tests.
- Work:
  - Add `async def create_controller(...)` that probes local HTTPS then falls back to HTTP for transport/SSL failures.
  - Add per-request SSL override support so HTTPS w/ self-signed certs can work without weakening other traffic.
  - Update docs/examples to recommend `create_controller` as the default entrypoint.
  - Add unit tests for probe behavior + endpoint construction.
- Verification (smallest signal):
  - `./script/test`
  - `.venv/bin/pre-commit run --all-files`
- Exit criteria: New API exists, tests pass, no cloud TLS regression.
- Rollback: Revert library commit(s).

## Phase 2 — Home Assistant integration switch-over
- Goal: HA calls library discovery; config flow remains unchanged.
- Work: TBD.
- Verification (smallest signal): HA integration tests + (optional) real-device manual check.
- Exit criteria: HA no longer needs to accept URL input; updated controllers connect.
- Rollback: Revert HA changes / pin dependency.

## Phase 3 — Release + cleanup
- Goal: Cut `pyrainbird` release; bump HA dependency; remove any now-redundant URL hacks.
- Work: TBD.
- Verification: existing CI + minimal smoke.
- Exit criteria: upstream merges + release shipped.
- Rollback: Revert dependency bump.

---

# 8) Verification Strategy (common-sense; non-blocking)

## 8.1 Unit tests (contracts)
- Lock scheme selection behavior and error taxonomy for probing.
- Lock local-only TLS relaxation behavior (must not affect cloud).

## 8.2 Integration tests (flows)
- HA config flow succeeds given either https-only or http-only mocked endpoints.

## 8.3 E2E / device tests (realistic)
- Manual: confirm with at least one updated controller (HTTPS/self-signed) and one legacy controller (HTTP) if available.

---

# 9) Rollout / Ops / Telemetry

## 9.1 Rollout plan
- No flags planned; rely on deterministic discovery.
- Rollback plan: revert commits or dependency bump.

## 9.2 Telemetry changes
- None planned (prefer debug logs).

## 9.3 Operational runbook
- Debug checklist: confirm chosen scheme, confirm TLS failure vs auth failure, confirm endpoint `/stick`.

---

# 10) Decision Log (append-only)

## 2026-02-21 — Move scheme discovery into `pyrainbird`
- Context: Updated controllers appear to require HTTPS; HA should not own URL semantics.
- Options:
  - A) HA probes schemes and stores URL.
  - B) `pyrainbird` probes schemes and returns ready controller (preferred).
- Decision: B.
- Consequences:
  - `pyrainbird` API grows a small factory surface.
  - HA stays simpler and stable for users.
- Follow-ups:
  - Define exact SSL policy boundaries (local-only) and error taxonomy for probing.

## 2026-02-21 — Local-only TLS relaxation is per-request
- Context: Updated controllers commonly present self-signed certs on local HTTPS; we must not weaken any non-local traffic.
- Options:
  - A) Set a connector-wide SSL policy (risk: leaks beyond the local controller calls).
  - B) Use per-request SSL overrides on the local client only (preferred).
- Decision: B (`aiohttp` request `ssl=` is set only for the local controller client when needed).
- Consequences:
  - HA can keep its shared `ClientSession` behavior (connector limit=1) unchanged.
  - `pyrainbird` must ensure retry-wrapped clients preserve the SSL policy.
