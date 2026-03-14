# RWS2 (RobotWare 7) Support — Design Plan

## Problem

`abb_robot_client` only supports RWS1 (RobotWare 6). RobotWare 7 uses a different HTTP
protocol variant (RWS2) with changes to authentication, URL structure, headers, and
mastership handling. Both must be supported from a single codebase.

## RWS1 vs RWS2 Protocol Differences

| Concern | RWS1 (RobotWare 6) | RWS2 (RobotWare 7) |
|---------|--------------------|--------------------|
| **Auth** | `HTTPDigestAuth` | `HTTPBasicAuth` |
| **Accept header** | (none) | `application/xhtml+xml;v=2.0` |
| **Content-Type** | (none) | `application/x-www-form-urlencoded;v=2.0` |
| **Action pattern** | `?action=verb` query param | `/verb` path segment |
| **Mastership** | explicit request/release | `?mastership=implicit` on mutating endpoints |
| **RAPID symbol path** | `/rw/rapid/symbol/data/RAPID/{task}/{var}` | `/rw/rapid/symbol/RAPID/{task}/{var}/data` |
| **Response format** | JSON via `?json=1` | JSON via `?json=1` (same — Schindler's XML is a regression) |

### Endpoint Mapping (exhaustive)

| Operation | RWS1 | RWS2 |
|-----------|------|------|
| start | `POST rw/rapid/execution?action=start` | `POST rw/rapid/execution/start?mastership=implicit` |
| stop | `POST rw/rapid/execution?action=stop` | `POST rw/rapid/execution/stop` |
| resetpp | `POST rw/rapid/execution?action=resetpp` | `POST rw/rapid/execution/resetpp?mastership=implicit` |
| activate_task | `POST rw/rapid/tasks/{t}?action=activate` | `POST rw/rapid/tasks/{t}/activate?mastership=implicit` |
| deactivate_task | `POST rw/rapid/tasks/{t}?action=deactivate` | `POST rw/rapid/tasks/{t}/deactivate?mastership=implicit` |
| set_ctrl_state | `POST rw/panel/ctrlstate?action=setctrlstate` | `POST rw/panel/ctrl-state` |
| set_speedratio | `POST rw/panel/speedratio?action=setspeedratio` | `POST rw/panel/speedratio?mastership=implicit` |
| get_ctrl_state | `GET rw/panel/ctrlstate` | `GET rw/panel/ctrl-state` |
| set_io | `POST rw/iosystem/signals/{n}/{u}/{s}?action=set` | `POST rw/iosystem/signals/{n}/{u}/{s}/set-value` |
| get_rapid_var | `GET rw/rapid/symbol/data/RAPID/{t}/{v}` | `GET rw/rapid/symbol/RAPID/{t}/{v}/data?value=1` |
| set_rapid_var | `POST rw/rapid/symbol/data/RAPID/{t}/{v}?action=set` | `POST rw/rapid/symbol/RAPID/{t}/{v}/data` |
| search_symbols | `POST rw/rapid/symbols?action=search-symbols` | `POST rw/rapid/symbols/search` |
| mastership_req | `POST rw/mastership` | `POST rw/mastership/request` |
| mastership_rel | `POST rw/mastership?action=release` | `POST rw/mastership/release` |
| rmmp_cancel | `POST users/rmmp?action=cancel` | `POST users/rmmp/cancel` |
| load_program | `POST rw/rapid/tasks/{t}/program?action=load` | `POST rw/rapid/tasks/{t}/program/load?mastership=implicit` |
| fileservice | `PUT/GET/DELETE fileservice/{path}` | same |
| elog | `GET rw/elog/{n}/?lang=en` | same |
| subscription | `POST subscription` | same (verify) |

> **Note**: Some RWS2 endpoints need verification against actual RW7 hardware. The
> Schindler reference and ABB developer docs are the sources; discrepancies should be
> resolved against hardware.

## Architecture

### Core Idea

All RWS1/RWS2 differences are **transport-level** (auth, headers, URL construction).
Business logic (response parsing, subscriptions, RMMP, type conversions) is identical.
Extract the variable parts into an `RWSProfile` — the RWS class becomes version-agnostic.

### New File: `src/abb_robot_client/rws_profile.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests

class RobotWareVersion(Enum):
    RW6 = "rw6"
    RW7 = "rw7"


@dataclass(frozen=True)
class RWSProfile:
    """Encapsulates all protocol differences between RWS1 and RWS2."""

    version: RobotWareVersion
    auth_class: type  # requests.auth.HTTPDigestAuth or HTTPBasicAuth
    headers: dict[str, str] = field(default_factory=dict)
    use_implicit_mastership: bool = False

    def url(self, operation: str, **fmt) -> str:
        """Map logical operation name to version-specific URL path.

        Parameters
        ----------
        operation : str
            Logical operation key (e.g. "start", "resetpp", "get_rapid_var")
        **fmt : str
            Format parameters (e.g. task="T_ROB1", var="my_var")
        """
        template = _ENDPOINTS[operation][self.version]
        return template.format(**fmt)

    def make_auth(self, username: str, password: str) -> requests.auth.AuthBase:
        return self.auth_class(username, password)


# --- Endpoint templates ---
# Keys are logical operation names, values map version to URL template.
# Templates use str.format() with named parameters.

_ENDPOINTS: dict[str, dict[RobotWareVersion, str]] = {
    # Execution control
    "start":           {RobotWareVersion.RW6: "rw/rapid/execution?action=start",
                        RobotWareVersion.RW7: "rw/rapid/execution/start?mastership=implicit"},
    "stop":            {RobotWareVersion.RW6: "rw/rapid/execution?action=stop",
                        RobotWareVersion.RW7: "rw/rapid/execution/stop"},
    "resetpp":         {RobotWareVersion.RW6: "rw/rapid/execution?action=resetpp",
                        RobotWareVersion.RW7: "rw/rapid/execution/resetpp?mastership=implicit"},
    "get_execution":   {RobotWareVersion.RW6: "rw/rapid/execution",
                        RobotWareVersion.RW7: "rw/rapid/execution"},

    # Task management
    "activate_task":   {RobotWareVersion.RW6: "rw/rapid/tasks/{task}?action=activate",
                        RobotWareVersion.RW7: "rw/rapid/tasks/{task}/activate?mastership=implicit"},
    "deactivate_task": {RobotWareVersion.RW6: "rw/rapid/tasks/{task}?action=deactivate",
                        RobotWareVersion.RW7: "rw/rapid/tasks/{task}/deactivate?mastership=implicit"},
    "get_tasks":       {RobotWareVersion.RW6: "rw/rapid/tasks",
                        RobotWareVersion.RW7: "rw/rapid/tasks"},

    # Panel
    "get_ctrl_state":  {RobotWareVersion.RW6: "rw/panel/ctrlstate",
                        RobotWareVersion.RW7: "rw/panel/ctrl-state"},
    "set_ctrl_state":  {RobotWareVersion.RW6: "rw/panel/ctrlstate?action=setctrlstate",
                        RobotWareVersion.RW7: "rw/panel/ctrl-state"},
    "get_opmode":      {RobotWareVersion.RW6: "rw/panel/opmode",
                        RobotWareVersion.RW7: "rw/panel/opmode"},
    "get_speedratio":  {RobotWareVersion.RW6: "rw/panel/speedratio",
                        RobotWareVersion.RW7: "rw/panel/speedratio"},
    "set_speedratio":  {RobotWareVersion.RW6: "rw/panel/speedratio?action=setspeedratio",
                        RobotWareVersion.RW7: "rw/panel/speedratio?mastership=implicit"},

    # IO
    "get_io":          {RobotWareVersion.RW6: "rw/iosystem/signals/{network}/{unit}/{signal}",
                        RobotWareVersion.RW7: "rw/iosystem/signals/{network}/{unit}/{signal}"},
    "set_io":          {RobotWareVersion.RW6: "rw/iosystem/signals/{network}/{unit}/{signal}?action=set",
                        RobotWareVersion.RW7: "rw/iosystem/signals/{network}/{unit}/{signal}/set-value"},

    # RAPID variables
    "get_rapid_var":   {RobotWareVersion.RW6: "rw/rapid/symbol/data/RAPID/{task}/{var}",
                        RobotWareVersion.RW7: "rw/rapid/symbol/RAPID/{task}/{var}/data?value=1"},
    "set_rapid_var":   {RobotWareVersion.RW6: "rw/rapid/symbol/data/RAPID/{task}/{var}?action=set",
                        RobotWareVersion.RW7: "rw/rapid/symbol/RAPID/{task}/{var}/data"},
    "search_symbols":  {RobotWareVersion.RW6: "rw/rapid/symbols?action=search-symbols",
                        RobotWareVersion.RW7: "rw/rapid/symbols/search"},

    # Motion
    "get_jointtarget": {RobotWareVersion.RW6: "rw/motionsystem/mechunits/{mechunit}/jointtarget",
                        RobotWareVersion.RW7: "rw/motionsystem/mechunits/{mechunit}/jointtarget"},
    "get_robtarget":   {RobotWareVersion.RW6: "rw/motionsystem/mechunits/{mechunit}/robtarget",
                        RobotWareVersion.RW7: "rw/motionsystem/mechunits/{mechunit}/robtarget"},

    # Mastership
    "mastership_req":  {RobotWareVersion.RW6: "rw/mastership",
                        RobotWareVersion.RW7: "rw/mastership/request"},
    "mastership_rel":  {RobotWareVersion.RW6: "rw/mastership?action=release",
                        RobotWareVersion.RW7: "rw/mastership/release"},

    # RMMP
    "rmmp":            {RobotWareVersion.RW6: "users/rmmp",
                        RobotWareVersion.RW7: "users/rmmp"},
    "rmmp_poll":       {RobotWareVersion.RW6: "users/rmmp/poll",
                        RobotWareVersion.RW7: "users/rmmp/poll"},

    # File service
    "fileservice":     {RobotWareVersion.RW6: "fileservice/{path}",
                        RobotWareVersion.RW7: "fileservice/{path}"},
    "ramdisk":         {RobotWareVersion.RW6: "ctrl/$RAMDISK",
                        RobotWareVersion.RW7: "ctrl/$RAMDISK"},

    # Event log
    "elog":            {RobotWareVersion.RW6: "rw/elog/{elog}/?lang=en",
                        RobotWareVersion.RW7: "rw/elog/{elog}/?lang=en"},

    # Program load
    "load_program":    {RobotWareVersion.RW6: "rw/rapid/tasks/{task}/program?action=load",
                        RobotWareVersion.RW7: "rw/rapid/tasks/{task}/program/load?mastership=implicit"},

    # Subscription
    "subscription":    {RobotWareVersion.RW6: "subscription",
                        RobotWareVersion.RW7: "subscription"},

    # Session
    "logout":          {RobotWareVersion.RW6: "logout",
                        RobotWareVersion.RW7: "logout"},

    # IPC / DIPC
    "dipc_create":     {RobotWareVersion.RW6: "rw/dipc?action=dipc-create",
                        RobotWareVersion.RW7: "rw/dipc/create"},
    "dipc_read":       {RobotWareVersion.RW6: "rw/dipc/{queue}?action=dipc-read",
                        RobotWareVersion.RW7: "rw/dipc/{queue}/read"},
    "dipc_send":       {RobotWareVersion.RW6: "rw/dipc/{queue}?action=dipc-send",
                        RobotWareVersion.RW7: "rw/dipc/{queue}/send"},
    "dipc_get":        {RobotWareVersion.RW6: "rw/dipc/{queue}",
                        RobotWareVersion.RW7: "rw/dipc/{queue}"},
}


# --- Profile factories ---

RW6_PROFILE = RWSProfile(
    version=RobotWareVersion.RW6,
    auth_class=None,  # resolved at import time, see below
)

RW7_PROFILE = RWSProfile(
    version=RobotWareVersion.RW7,
    auth_class=None,
    headers={
        "Accept": "application/xhtml+xml;v=2.0",
        "Content-Type": "application/x-www-form-urlencoded;v=2.0",
    },
    use_implicit_mastership=True,
)


def detect_robotware_version(base_url: str, username: str, password: str) -> RobotWareVersion:
    """Probe controller to determine RobotWare version.

    Strategy: GET /rw/system with Basic auth. If 200, it's RW7.
    If 401, try Digest auth — if 200, it's RW6.
    """
    ...
```

### Changes to `rws.py`

Minimal, surgical changes — no rewrite:

**1. Constructor** — accept optional `version` parameter:

```python
def __init__(self, base_url='http://127.0.0.1:80',
             username=None, password=None,
             version: RobotWareVersion | None = None):
    self.base_url = base_url
    if username is None:
        username = 'Default User'
    if password is None:
        password = 'robotics'

    if version is None:
        version = detect_robotware_version(base_url, username, password)

    self._profile = _make_profile(version)
    self.auth = self._profile.make_auth(username, password)
    self._session = requests.Session()
    if self._profile.headers:
        self._session.headers.update(self._profile.headers)
```

**2. URL construction** — replace hardcoded strings:

```python
# Before:
def start(self, cycle='asis', tasks=['T_ROB1']):
    ...
    self._do_post("rw/rapid/execution?action=start", payload)

# After:
def start(self, cycle='asis', tasks=['T_ROB1']):
    ...
    self._do_post(self._profile.url("start"), payload)
```

**3. Every method** — same mechanical replacement. Full list:

| Method | Old URL | Profile key |
|--------|---------|-------------|
| `start()` | `rw/rapid/execution?action=start` | `start` |
| `stop()` | `rw/rapid/execution?action=stop` | `stop` |
| `resetpp()` | `rw/rapid/execution?action=resetpp` | `resetpp` |
| `activate_task()` | `rw/rapid/tasks/{t}?action=activate` | `activate_task` |
| `deactivate_task()` | `rw/rapid/tasks/{t}?action=deactivate` | `deactivate_task` |
| `get_execution_state()` | `rw/rapid/execution` | `get_execution` |
| `get_controller_state()` | `rw/panel/ctrlstate` | `get_ctrl_state` |
| `set_controller_state()` | `rw/panel/ctrlstate?action=setctrlstate` | `set_ctrl_state` |
| `get_operation_mode()` | `rw/panel/opmode` | `get_opmode` |
| `get_speedratio()` | `rw/panel/speedratio` | `get_speedratio` |
| `set_speedratio()` | `rw/panel/speedratio?action=setspeedratio` | `set_speedratio` |
| `get_digital_io()` | `rw/iosystem/signals/...` | `get_io` |
| `set_digital_io()` | `rw/iosystem/signals/...?action=set` | `set_io` |
| `get_analog_io()` | `rw/iosystem/signals/...` | `get_io` |
| `set_analog_io()` | `rw/iosystem/signals/...?action=set` | `set_io` |
| `get_rapid_variable()` | `rw/rapid/symbol/data/RAPID/...` | `get_rapid_var` |
| `set_rapid_variable()` | `rw/rapid/symbol/data/RAPID/...?action=set` | `set_rapid_var` |
| `get_rapid_variables()` | `rw/rapid/symbols?action=search-symbols` | `search_symbols` |
| `get_jointtarget()` | `rw/motionsystem/mechunits/...` | `get_jointtarget` |
| `get_robtarget()` | `rw/motionsystem/mechunits/...` | `get_robtarget` |
| `read_event_log()` | `rw/elog/...` | `elog` |
| `read_file()` | `fileservice/...` | `fileservice` |
| `upload_file()` | `fileservice/...` | `fileservice` |
| `delete_file()` | `fileservice/...` | `fileservice` |
| `list_files()` | `fileservice/...` | `fileservice` |
| `get_ramdisk_path()` | `ctrl/$RAMDISK` | `ramdisk` |
| `subscribe()` | `subscription` | `subscription` |
| `request_rmmp()` | `users/rmmp` | `rmmp` |
| `poll_rmmp()` | `users/rmmp/poll` | `rmmp_poll` |
| `logout()` | `logout` | `logout` |
| IPC methods | `rw/dipc/...` | `dipc_*` |

### Changes to `rws_aio.py`

Identical pattern — same profile-based URL lookup. The async client uses `httpx.DigestAuth`;
for RW7 it switches to `httpx.BasicAuth`.

### Changes to `abb_motion_program_exec`

Minimal — pass through `version` parameter:

```python
class MotionProgramExecClient:
    def __init__(self, base_url='http://127.0.0.1:80',
                 username=None, password=None,
                 version=None):  # NEW
        from abb_robot_client.rws import RWS
        self.abb_client = RWS(base_url, username, password, version=version)
```

Everything else works unchanged — the binary protocol, motion program serialization,
event log parsing, IO signal names are all ABB firmware features, not RWS version features.

## Quality Fixes (opportunistic, same PR)

These are bugs/smells in the current code worth fixing in the same pass:

1. **Bug**: `rws.py:232` — duplicate `status_code == 503` check; first should be `500`
2. **Bare `except:`** at lines 245, 575, 579, 904, 1013, 1018 — replace with specific exceptions
3. **`_process_response`** bare `except:` on JSON parse — replace with `except ValueError:`
4. **Add `__all__`** to `__init__.py` for clean public API

## Implementation Steps

### Step 1: Create `rws_profile.py`
- `RobotWareVersion` enum
- `RWSProfile` dataclass
- `_ENDPOINTS` mapping dict
- `RW6_PROFILE`, `RW7_PROFILE` factory constants
- `detect_robotware_version()` function
- Unit tests for endpoint mapping (no hardware needed)

### Step 2: Modify `rws.py` — constructor + `_do_get`/`_do_post`
- Add `version` parameter to `__init__`
- Create profile, set auth and headers from profile
- Modify `_do_get` and `_do_post` to handle RWS2 header behavior
  (RWS2 sets Accept/Content-Type differently, `?json=1` may need adjustment)
- Fix the 500/503 bug
- Replace bare `except:` clauses

### Step 3: Modify `rws.py` — replace all hardcoded URLs
- Mechanical: replace every URL string with `self._profile.url("key", **params)`
- One method at a time, preserving exact behavior for RW6

### Step 4: Modify `rws_aio.py` — same changes
- Mirror steps 2-3 for async client
- Switch `httpx.DigestAuth` / `httpx.BasicAuth` based on profile

### Step 5: Auto-detection
- Implement `detect_robotware_version()` — probe controller
- Add timeout/fallback behavior
- Test against both RW6 and RW7 (may need RobotStudio instances)

### Step 6: Integration test with `abb_motion_program_exec`
- Add `version` pass-through to `MotionProgramExecClient`
- Verify motion program upload/execute cycle works on RW7
- Verify event log parsing works on RW7

### Step 7: Documentation
- Update README with RW7 support
- Document `RobotWareVersion` enum in API docs
- Add migration guide for users upgrading from RW6 to RW7

## Open Questions (verify against hardware)

1. **Subscription WebSocket**: Does RW7 use the same `robapi2_subscription` subprotocol?
2. **Event log format**: Same JSON structure in RW7?
3. **RMMP flow**: Same request→poll cycle in RW7?
4. **`?json=1`**: Does RW7 still honor this, or is JSON the default?
5. **File service**: PUT semantics identical?
6. **EGM (UDP)**: Any changes in RW7? (likely not — EGM is separate from RWS)

These must be verified against a RobotWare 7 controller or RobotStudio 7 instance
before the endpoint map is finalized.

## Non-Goals

- **Sync/async unification**: The code duplication between `rws.py` and `rws_aio.py` is
  a real problem but orthogonal to RWS2 support. Separate initiative.
- **Adopting Schindler code**: AGPL-3.0 licensed, poor quality. Used only as protocol
  reference — no code adopted.
- **New features only in RW7**: Lead-through mode, etc. — add later, gate behind
  `RobotWareVersion.RW7` checks.
