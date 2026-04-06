# Copyright 2022 Wason Technology LLC, Rensselaer Polytechnic Institute
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Literal

import requests
import requests.auth


class RobotWareVersion(Enum):
    """RobotWare major version determining the RWS protocol variant."""

    RW6 = "rw6"
    RW7 = "rw7"


@dataclass(frozen=True)
class RWSProfile:
    """Encapsulates all protocol differences between RWS1 (RW6) and RWS2 (RW7).

    This is the single point of variation — the RWS/RWS_AIO classes become
    version-agnostic by delegating auth, headers, and URL construction here.
    """

    version: RobotWareVersion
    auth_type: Literal["digest", "basic"]
    headers: MappingProxyType[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def url(self, operation: str, **fmt: str) -> str:
        """Map logical operation name to version-specific URL path.

        Parameters
        ----------
        operation
            Logical operation key (e.g. ``"start"``, ``"get_rapid_var"``).
        **fmt
            Format parameters (e.g. ``task="T_ROB1"``, ``var="my_var"``).
        """
        template = _ENDPOINTS[operation][self.version]
        return template.format(**fmt) if fmt else template


# ---------------------------------------------------------------------------
# Endpoint templates
# ---------------------------------------------------------------------------
# Keys are logical operation names, values map version → URL template.
# Templates use str.format() with named parameters.

# Built as dict, then frozen to MappingProxyType after validation below
_ENDPOINTS: MappingProxyType[str, MappingProxyType[RobotWareVersion, str]]
_ENDPOINTS = {
    # Execution control
    "start": {
        RobotWareVersion.RW6: "rw/rapid/execution?action=start",
        RobotWareVersion.RW7: "rw/rapid/execution/start?mastership=implicit",
    },
    "stop": {
        RobotWareVersion.RW6: "rw/rapid/execution?action=stop",
        RobotWareVersion.RW7: "rw/rapid/execution/stop",
    },
    "resetpp": {
        RobotWareVersion.RW6: "rw/rapid/execution?action=resetpp",
        RobotWareVersion.RW7: "rw/rapid/execution/resetpp?mastership=implicit",
    },
    "get_execution": {
        RobotWareVersion.RW6: "rw/rapid/execution",
        RobotWareVersion.RW7: "rw/rapid/execution",
    },
    # Task management
    "activate_task": {
        RobotWareVersion.RW6: "rw/rapid/tasks/{task}?action=activate",
        RobotWareVersion.RW7: "rw/rapid/tasks/{task}/activate?mastership=implicit",
    },
    "deactivate_task": {
        RobotWareVersion.RW6: "rw/rapid/tasks/{task}?action=deactivate",
        RobotWareVersion.RW7: "rw/rapid/tasks/{task}/deactivate?mastership=implicit",
    },
    "get_tasks": {
        RobotWareVersion.RW6: "rw/rapid/tasks",
        RobotWareVersion.RW7: "rw/rapid/tasks",
    },
    # Panel
    "get_ctrl_state": {
        RobotWareVersion.RW6: "rw/panel/ctrlstate",
        RobotWareVersion.RW7: "rw/panel/ctrl-state",
    },
    "set_ctrl_state": {
        RobotWareVersion.RW6: "rw/panel/ctrlstate?action=setctrlstate",
        RobotWareVersion.RW7: "rw/panel/ctrl-state",
    },
    "get_opmode": {
        RobotWareVersion.RW6: "rw/panel/opmode",
        RobotWareVersion.RW7: "rw/panel/opmode",
    },
    "get_speedratio": {
        RobotWareVersion.RW6: "rw/panel/speedratio",
        RobotWareVersion.RW7: "rw/panel/speedratio",
    },
    "set_speedratio": {
        RobotWareVersion.RW6: "rw/panel/speedratio?action=setspeedratio",
        RobotWareVersion.RW7: "rw/panel/speedratio?mastership=implicit",
    },
    # IO
    "get_io": {
        RobotWareVersion.RW6: "rw/iosystem/signals/{network}/{unit}/{signal}",
        RobotWareVersion.RW7: "rw/iosystem/signals/{network}/{unit}/{signal}",
    },
    "set_io": {
        RobotWareVersion.RW6: "rw/iosystem/signals/{network}/{unit}/{signal}?action=set",
        RobotWareVersion.RW7: "rw/iosystem/signals/{network}/{unit}/{signal}/set-value",
    },
    # RAPID variables
    "get_rapid_var": {
        RobotWareVersion.RW6: "rw/rapid/symbol/data/RAPID/{var}",
        RobotWareVersion.RW7: "rw/rapid/symbol/RAPID/{var}/data?value=1",
    },
    "set_rapid_var": {
        RobotWareVersion.RW6: "rw/rapid/symbol/data/RAPID/{var}?action=set",
        RobotWareVersion.RW7: "rw/rapid/symbol/RAPID/{var}/data",
    },
    "search_symbols": {
        RobotWareVersion.RW6: "rw/rapid/symbols?action=search-symbols",
        RobotWareVersion.RW7: "rw/rapid/symbols/search",
    },
    # Motion
    "get_jointtarget": {
        RobotWareVersion.RW6: "rw/motionsystem/mechunits/{mechunit}/jointtarget",
        RobotWareVersion.RW7: "rw/motionsystem/mechunits/{mechunit}/jointtarget",
    },
    "get_robtarget": {
        RobotWareVersion.RW6: "rw/motionsystem/mechunits/{mechunit}/robtarget",
        RobotWareVersion.RW7: "rw/motionsystem/mechunits/{mechunit}/robtarget",
    },
    # Mastership (not yet called from rws.py — reserved for explicit mastership API)
    "mastership_req": {
        RobotWareVersion.RW6: "rw/mastership",
        RobotWareVersion.RW7: "rw/mastership/request",
    },
    "mastership_rel": {
        RobotWareVersion.RW6: "rw/mastership?action=release",
        RobotWareVersion.RW7: "rw/mastership/release",
    },
    # RMMP
    "rmmp": {
        RobotWareVersion.RW6: "users/rmmp",
        RobotWareVersion.RW7: "users/rmmp",
    },
    "rmmp_poll": {
        RobotWareVersion.RW6: "users/rmmp/poll",
        RobotWareVersion.RW7: "users/rmmp/poll",
    },
    "rmmp_cancel": {
        RobotWareVersion.RW6: "users/rmmp?action=cancel",
        RobotWareVersion.RW7: "users/rmmp/cancel",
    },
    # File service
    "fileservice": {
        RobotWareVersion.RW6: "fileservice/{path}",
        RobotWareVersion.RW7: "fileservice/{path}",
    },
    "ramdisk": {
        RobotWareVersion.RW6: "ctrl/$RAMDISK",
        RobotWareVersion.RW7: "ctrl/$RAMDISK",
    },
    # Event log
    "elog": {
        RobotWareVersion.RW6: "rw/elog/{elog}/?lang=en",
        RobotWareVersion.RW7: "rw/elog/{elog}/?lang=en",
    },
    # Program load (not yet called from rws.py — reserved for program management API)
    "load_program": {
        RobotWareVersion.RW6: "rw/rapid/tasks/{task}/program?action=load",
        RobotWareVersion.RW7: "rw/rapid/tasks/{task}/program/load?mastership=implicit",
    },
    # Subscription
    "subscription": {
        RobotWareVersion.RW6: "subscription",
        RobotWareVersion.RW7: "subscription",
    },
    # Session
    "logout": {
        RobotWareVersion.RW6: "logout",
        RobotWareVersion.RW7: "logout",
    },
    # Subscription resource paths (with leading / and ;attr suffix)
    "sub_ctrl_state": {
        RobotWareVersion.RW6: "/rw/panel/ctrlstate",
        RobotWareVersion.RW7: "/rw/panel/ctrl-state",
    },
    "sub_opmode": {
        RobotWareVersion.RW6: "/rw/panel/opmode",
        RobotWareVersion.RW7: "/rw/panel/opmode",
    },
    "sub_execution": {
        RobotWareVersion.RW6: "/rw/rapid/execution;ctrlexecstate",
        RobotWareVersion.RW7: "/rw/rapid/execution;ctrlexecstate",
    },
    "sub_pers_var": {
        RobotWareVersion.RW6: "/rw/rapid/symbol/data/RAPID/{var};value",
        RobotWareVersion.RW7: "/rw/rapid/symbol/RAPID/{var}/data;value",
    },
    "sub_ipc": {
        RobotWareVersion.RW6: "/rw/dipc/{queue}",
        RobotWareVersion.RW7: "/rw/dipc/{queue}",
    },
    "sub_elog": {
        RobotWareVersion.RW6: "/rw/elog/0",
        RobotWareVersion.RW7: "/rw/elog/0",
    },
    "sub_signal": {
        RobotWareVersion.RW6: "/rw/iosystem/signals/{network}/{unit}/{signal};state",
        RobotWareVersion.RW7: "/rw/iosystem/signals/{network}/{unit}/{signal};state",
    },
    # IPC / DIPC
    "dipc_create": {
        RobotWareVersion.RW6: "rw/dipc?action=dipc-create",
        RobotWareVersion.RW7: "rw/dipc/create",
    },
    "dipc_read": {
        RobotWareVersion.RW6: "rw/dipc/{queue}?action=dipc-read",
        RobotWareVersion.RW7: "rw/dipc/{queue}/read",
    },
    "dipc_send": {
        RobotWareVersion.RW6: "rw/dipc/{queue}?action=dipc-send",
        RobotWareVersion.RW7: "rw/dipc/{queue}/send",
    },
    "dipc_get": {
        RobotWareVersion.RW6: "rw/dipc/{queue}",
        RobotWareVersion.RW7: "rw/dipc/{queue}",
    },
}

# Validate completeness and freeze — both the inner dicts and the outer dict
_all_versions = set(RobotWareVersion)
for _op, _mapping in _ENDPOINTS.items():
    _missing = _all_versions - _mapping.keys()
    if _missing:
        raise ValueError(f"_ENDPOINTS[{_op!r}] missing versions: {_missing}")
_ENDPOINTS = MappingProxyType(
    {k: MappingProxyType(v) for k, v in _ENDPOINTS.items()}
)
del _all_versions, _op, _mapping, _missing

# ---------------------------------------------------------------------------
# Profile constants and factories
# ---------------------------------------------------------------------------

RW6_PROFILE = RWSProfile(
    version=RobotWareVersion.RW6,
    auth_type="digest",
)

RW7_PROFILE = RWSProfile(
    version=RobotWareVersion.RW7,
    auth_type="basic",
    headers=MappingProxyType(
        {
            "Accept": "application/xhtml+xml;v=2.0",
            "Content-Type": "application/x-www-form-urlencoded;v=2.0",
        }
    ),
)


def _make_profile(version: RobotWareVersion) -> RWSProfile:
    """Return the canonical profile for a RobotWare version."""
    if version is RobotWareVersion.RW6:
        return RW6_PROFILE
    if version is RobotWareVersion.RW7:
        return RW7_PROFILE
    raise ValueError(f"Unknown RobotWare version: {version}")


def detect_robotware_version(
    base_url: str, username: str, password: str
) -> RobotWareVersion:
    """Probe controller to determine RobotWare version.

    Strategy: GET ``/rw/system`` with Basic auth.
    If 200 → RW7.  If 401 → try Digest auth; if 200 → RW6.
    """
    # Try Basic auth first (RW7)
    resp = requests.get(
        f"{base_url}/rw/system",
        auth=requests.auth.HTTPBasicAuth(username, password),
        timeout=5,
    )
    if resp.status_code == 200:
        return RobotWareVersion.RW7
    if resp.status_code != 401:
        raise RuntimeError(
            f"Unexpected HTTP {resp.status_code} from {base_url}/rw/system "
            f"during version detection (Basic auth)"
        )

    # 401 from Basic → try Digest auth (RW6)
    resp = requests.get(
        f"{base_url}/rw/system",
        auth=requests.auth.HTTPDigestAuth(username, password),
        timeout=5,
    )
    if resp.status_code == 200:
        return RobotWareVersion.RW6

    raise RuntimeError(
        f"Cannot determine RobotWare version at {base_url} — "
        f"Digest auth returned HTTP {resp.status_code}"
    )
