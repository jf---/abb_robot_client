"""Unit tests for RWSProfile — the strategy layer that encapsulates RWS1/RWS2 differences.

These tests verify the endpoint mapping, URL generation, and profile construction
*without* requiring a robot controller or RobotStudio instance. They are the primary
safety net ensuring that the mapping table in rws_profile.py correctly encodes the
ABB RWS protocol differences documented in the design plan.
"""

import pytest

from abb_robot_client.rws_profile import (
    RobotWareVersion,
    RW6_PROFILE,
    RW7_PROFILE,
    _ENDPOINTS,
    _make_profile,
)


class TestRobotWareVersion:
    """RobotWareVersion enum must have exactly two members with stable string values.

    The string values are used in logging/serialization — changing them would be a
    breaking change for any code that persists or displays the version.
    """

    def test_values(self):
        assert RobotWareVersion.RW6.value == "rw6"
        assert RobotWareVersion.RW7.value == "rw7"

    def test_enum_members(self):
        """Guard against accidental addition/removal of enum members."""
        assert set(RobotWareVersion) == {RobotWareVersion.RW6, RobotWareVersion.RW7}


class TestRWSProfile:
    """Verify the pre-built profile constants carry the correct auth and header config.

    RW6 uses HTTP Digest auth with no special headers.
    RW7 uses HTTP Basic auth and requires Accept/Content-Type headers with version tags.
    """

    def test_rw6_profile_auth(self):
        """RW6 (RobotWare 6) uses Digest auth, no extra headers."""
        assert RW6_PROFILE.auth_type == "digest"
        assert RW6_PROFILE.version is RobotWareVersion.RW6
        assert len(RW6_PROFILE.headers) == 0

    def test_rw7_profile_auth(self):
        """RW7 (RobotWare 7) uses Basic auth with versioned Accept/Content-Type."""
        assert RW7_PROFILE.auth_type == "basic"
        assert RW7_PROFILE.version is RobotWareVersion.RW7
        assert "Accept" in RW7_PROFILE.headers
        assert "Content-Type" in RW7_PROFILE.headers

    def test_frozen(self):
        """Profiles are frozen dataclasses — mutation would corrupt shared state."""
        with pytest.raises(AttributeError):
            RW6_PROFILE.version = RobotWareVersion.RW7


class TestMakeProfile:
    """_make_profile must return the canonical singleton for each version.

    Returning singletons (not copies) means identity checks work and there's
    exactly one source of truth per version.
    """

    def test_rw6(self):
        assert _make_profile(RobotWareVersion.RW6) is RW6_PROFILE

    def test_rw7(self):
        assert _make_profile(RobotWareVersion.RW7) is RW7_PROFILE


class TestEndpointCompleteness:
    """Every endpoint key in _ENDPOINTS must have templates for both RW6 and RW7.

    A missing version entry would cause a KeyError at runtime when a user connects
    to that controller version. These tests catch that at import time.
    """

    def test_all_keys_have_both_versions(self):
        """Prevent partial entries — every operation must map both versions."""
        for key, versions in _ENDPOINTS.items():
            assert RobotWareVersion.RW6 in versions, f"{key} missing RW6"
            assert RobotWareVersion.RW7 in versions, f"{key} missing RW7"

    def test_no_empty_templates(self):
        """Empty strings would produce broken URLs silently."""
        for key, versions in _ENDPOINTS.items():
            for ver, template in versions.items():
                assert template, f"{key}/{ver.value} has empty template"


class TestUrlGeneration:
    """Verify url() correctly resolves str.format() templates for both versions.

    These tests use representative endpoints (simple, task-parameterized,
    multi-param IO) to exercise the template engine without testing every
    individual endpoint — that's covered by TestEndpointCompleteness.
    """

    @pytest.mark.parametrize("version", [RobotWareVersion.RW6, RobotWareVersion.RW7])
    def test_simple_endpoint(self, version):
        """Endpoints with no format params should resolve without arguments."""
        profile = _make_profile(version)
        url = profile.url("start")
        assert "rapid/execution" in url

    @pytest.mark.parametrize("version", [RobotWareVersion.RW6, RobotWareVersion.RW7])
    def test_parameterized_endpoint_task(self, version):
        """The {task} placeholder must be substituted, not left as a literal."""
        profile = _make_profile(version)
        url = profile.url("activate_task", task="T_ROB1")
        assert "T_ROB1" in url
        assert "{task}" not in url

    @pytest.mark.parametrize("version", [RobotWareVersion.RW6, RobotWareVersion.RW7])
    def test_parameterized_endpoint_io(self, version):
        """IO endpoints take three params — all must appear in the resolved URL."""
        profile = _make_profile(version)
        url = profile.url("set_io", network="Local", unit="DRV_1", signal="do_1")
        assert "Local" in url
        assert "DRV_1" in url
        assert "do_1" in url

    @pytest.mark.parametrize("version", [RobotWareVersion.RW6, RobotWareVersion.RW7])
    def test_rapid_var_path(self, version):
        """RAPID variable paths include task/module/varname — all must survive formatting."""
        profile = _make_profile(version)
        url = profile.url("get_rapid_var", var="T_ROB1/Module1/myvar")
        assert "T_ROB1/Module1/myvar" in url

    def test_unknown_operation_raises(self):
        """Typos in operation names must fail fast, not produce silent bugs."""
        with pytest.raises(KeyError):
            RW6_PROFILE.url("nonexistent_operation")


class TestRW6VsRW7Differences:
    """Verify the specific protocol differences between RWS1 and RWS2.

    These are the critical behavioral differences documented in the ABB developer
    docs and the Schindler reference. Each test maps to a row in the design plan's
    endpoint comparison table.
    """

    def test_action_pattern_rw6(self):
        """RW6 uses ?action=verb query parameter pattern."""
        url = RW6_PROFILE.url("start")
        assert "?action=start" in url

    def test_action_pattern_rw7(self):
        """RW7 uses /verb path segment pattern instead of ?action=verb."""
        url = RW7_PROFILE.url("start")
        assert "/start" in url
        assert "?action=" not in url

    def test_mastership_implicit_rw7(self):
        """RW7 mutating endpoints use ?mastership=implicit instead of explicit mastership."""
        url = RW7_PROFILE.url("start")
        assert "mastership=implicit" in url

    def test_no_mastership_rw6(self):
        """RW6 start endpoint does not include mastership — it's handled separately."""
        url = RW6_PROFILE.url("start")
        assert "mastership" not in url

    def test_ctrl_state_path_differs(self):
        """RW7 renamed 'ctrlstate' → 'ctrl-state' (hyphenated)."""
        assert "ctrlstate" in RW6_PROFILE.url("get_ctrl_state")
        assert "ctrl-state" in RW7_PROFILE.url("get_ctrl_state")

    def test_set_io_differs(self):
        """RW6: ?action=set query param. RW7: /set-value path segment."""
        kw = {"network": "Local", "unit": "DRV_1", "signal": "do_1"}
        rw6 = RW6_PROFILE.url("set_io", **kw)
        rw7 = RW7_PROFILE.url("set_io", **kw)
        assert "?action=set" in rw6
        assert "/set-value" in rw7

    def test_rapid_symbol_path_differs(self):
        """RW6: /symbol/data/RAPID/{var}. RW7: /symbol/RAPID/{var}/data — inverted nesting."""
        rw6 = RW6_PROFILE.url("get_rapid_var", var="T_ROB1/myvar")
        rw7 = RW7_PROFILE.url("get_rapid_var", var="T_ROB1/myvar")
        assert rw6.startswith("rw/rapid/symbol/data/RAPID/")
        assert rw7.startswith("rw/rapid/symbol/RAPID/")
        assert rw7.endswith("/data?value=1")

    def test_dipc_create_differs(self):
        """RW6: ?action=dipc-create. RW7: /create path segment."""
        assert "?action=dipc-create" in RW6_PROFILE.url("dipc_create")
        assert "/create" in RW7_PROFILE.url("dipc_create")

    def test_subscription_pers_var_path_differs(self):
        """Subscription resource paths mirror the RAPID symbol path difference."""
        rw6 = RW6_PROFILE.url("sub_pers_var", var="T_ROB1/myvar")
        rw7 = RW7_PROFILE.url("sub_pers_var", var="T_ROB1/myvar")
        assert "/rw/rapid/symbol/data/RAPID/" in rw6
        assert "/rw/rapid/symbol/RAPID/" in rw7

    def test_identical_endpoints_stay_identical(self):
        """Some endpoints (execution, tasks, opmode, etc.) are the same in both versions.

        This test prevents accidental divergence — if ABB changes one of these in a
        future RW7 update, this test will need updating with the new path.
        """
        for key in (
            "get_execution",
            "get_tasks",
            "get_opmode",
            "get_speedratio",
            "ramdisk",
            "subscription",
            "logout",
            "rmmp",
            "rmmp_poll",
        ):
            rw6 = (
                RW6_PROFILE.url(key)
                if "{" not in _ENDPOINTS[key][RobotWareVersion.RW6]
                else None
            )
            rw7 = (
                RW7_PROFILE.url(key)
                if "{" not in _ENDPOINTS[key][RobotWareVersion.RW7]
                else None
            )
            if rw6 is not None and rw7 is not None:
                assert rw6 == rw7, f"{key}: RW6={rw6} != RW7={rw7}"


class TestRW6BackwardCompatibility:
    """Verify that RW6 profile URLs exactly match the old hardcoded strings.

    Before the profile refactoring, every URL was a literal string in rws.py.
    This test ensures the profile produces identical URLs, preventing regressions
    that would break existing RW6 deployments.
    """

    @pytest.mark.parametrize(
        "op,kwargs,expected",
        [
            ("start", {}, "rw/rapid/execution?action=start"),
            ("stop", {}, "rw/rapid/execution?action=stop"),
            ("resetpp", {}, "rw/rapid/execution?action=resetpp"),
            ("get_execution", {}, "rw/rapid/execution"),
            (
                "activate_task",
                {"task": "T_ROB1"},
                "rw/rapid/tasks/T_ROB1?action=activate",
            ),
            (
                "deactivate_task",
                {"task": "T_ROB1"},
                "rw/rapid/tasks/T_ROB1?action=deactivate",
            ),
            ("get_tasks", {}, "rw/rapid/tasks"),
            ("get_ctrl_state", {}, "rw/panel/ctrlstate"),
            ("set_ctrl_state", {}, "rw/panel/ctrlstate?action=setctrlstate"),
            ("get_opmode", {}, "rw/panel/opmode"),
            ("get_speedratio", {}, "rw/panel/speedratio"),
            ("set_speedratio", {}, "rw/panel/speedratio?action=setspeedratio"),
            (
                "get_io",
                {"network": "Local", "unit": "DRV_1", "signal": "do1"},
                "rw/iosystem/signals/Local/DRV_1/do1",
            ),
            (
                "set_io",
                {"network": "Local", "unit": "DRV_1", "signal": "do1"},
                "rw/iosystem/signals/Local/DRV_1/do1?action=set",
            ),
            (
                "get_rapid_var",
                {"var": "T_ROB1/myvar"},
                "rw/rapid/symbol/data/RAPID/T_ROB1/myvar",
            ),
            (
                "set_rapid_var",
                {"var": "T_ROB1/myvar"},
                "rw/rapid/symbol/data/RAPID/T_ROB1/myvar?action=set",
            ),
            ("search_symbols", {}, "rw/rapid/symbols?action=search-symbols"),
            (
                "get_jointtarget",
                {"mechunit": "ROB_1"},
                "rw/motionsystem/mechunits/ROB_1/jointtarget",
            ),
            (
                "get_robtarget",
                {"mechunit": "ROB_1"},
                "rw/motionsystem/mechunits/ROB_1/robtarget",
            ),
            ("ramdisk", {}, "ctrl/$RAMDISK"),
            ("elog", {"elog": "0"}, "rw/elog/0/?lang=en"),
            ("fileservice", {"path": "HOME/test.mod"}, "fileservice/HOME/test.mod"),
            ("rmmp", {}, "users/rmmp"),
            ("rmmp_poll", {}, "users/rmmp/poll"),
            ("subscription", {}, "subscription"),
            ("logout", {}, "logout"),
            ("dipc_create", {}, "rw/dipc?action=dipc-create"),
            ("dipc_read", {"queue": "myq"}, "rw/dipc/myq?action=dipc-read"),
            ("dipc_send", {"queue": "myq"}, "rw/dipc/myq?action=dipc-send"),
            ("dipc_get", {"queue": "myq"}, "rw/dipc/myq"),
        ],
        ids=lambda x: x if isinstance(x, str) and not x.startswith("rw") else "",
    )
    def test_rw6_url_matches_original(self, op, kwargs, expected):
        """Each RW6 profile URL must exactly match the old hardcoded string."""
        assert RW6_PROFILE.url(op, **kwargs) == expected


class TestSubscriptionRegexCompat:
    """Verify WebSocket message parsing regexes match both RW6 and RW7 path formats.

    The subscription setup uses versioned paths, and the controller echoes those
    paths in WebSocket messages. The regexes must handle both formats to avoid
    silently dropping all events on one version.
    """

    @pytest.fixture()
    def ctrl_re(self):
        import re

        return re.compile(
            r'<a\s+href="/rw/panel/ctrl-?state"\s+rel="self"/?>.*<span\s+class="ctrlstate">([^<]+)<'
        )

    @pytest.fixture()
    def pers_re(self):
        import re

        return re.compile(
            r'<a\s+href="/rw/rapid/symbol/(?:data/)?RAPID/([^";]+?)(?:/data)?;value"\s+rel="self"/?>.*<span\s+class="value">([^<]+)<'
        )

    def test_ctrl_re_matches_rw6(self, ctrl_re):
        """RW6 controller state path: /rw/panel/ctrlstate"""
        msg = '<li class="pnl-ctrlstate-ev"><a href="/rw/panel/ctrlstate" rel="self"/><span class="ctrlstate">motoron</span></li>'
        m = ctrl_re.search(msg)
        assert m is not None
        assert m.group(1) == "motoron"

    def test_ctrl_re_matches_rw7(self, ctrl_re):
        """RW7 controller state path: /rw/panel/ctrl-state (hyphenated)"""
        msg = '<li class="pnl-ctrlstate-ev"><a href="/rw/panel/ctrl-state" rel="self"/><span class="ctrlstate">motoron</span></li>'
        m = ctrl_re.search(msg)
        assert m is not None
        assert m.group(1) == "motoron"

    def test_pers_re_matches_rw6(self, pers_re):
        """RW6 pers var path: /rw/rapid/symbol/data/RAPID/{task}/{var};value"""
        msg = '<li class="rap-data"><a href="/rw/rapid/symbol/data/RAPID/T_ROB1/Module1/myvar;value" rel="self"/><span class="value">42</span></li>'
        m = pers_re.search(msg)
        assert m is not None
        assert m.group(1) == "T_ROB1/Module1/myvar"
        assert m.group(2) == "42"

    def test_pers_re_matches_rw7(self, pers_re):
        """RW7 pers var path: /rw/rapid/symbol/RAPID/{task}/{var}/data;value"""
        msg = '<li class="rap-data"><a href="/rw/rapid/symbol/RAPID/T_ROB1/Module1/myvar/data;value" rel="self"/><span class="value">42</span></li>'
        m = pers_re.search(msg)
        assert m is not None
        assert m.group(1) == "T_ROB1/Module1/myvar"
        assert m.group(2) == "42"


class TestUrlCallSiteCrossReference:
    """Verify every url() call in rws.py and rws_aio.py uses a valid endpoint key.

    A typo like url("strat") instead of url("start") would only crash at runtime
    when that specific code path runs on a production robot. This test statically
    extracts all operation keys from the source and validates them against _ENDPOINTS.
    """

    @staticmethod
    def _extract_url_keys(filepath: str) -> list[tuple[str, int]]:
        """Parse source file for all .url("key" calls, return (key, line_number) pairs."""
        import ast
        from pathlib import Path

        source = Path(filepath).read_text()
        tree = ast.parse(source)
        keys = []
        for node in ast.walk(tree):
            # Match: self._profile.url("key", ...) or PROFILE.url("key", ...)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "url"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.append((node.args[0].value, node.lineno))
        return keys

    def test_rws_url_keys_all_valid(self):
        """Every url() call in rws.py must reference a key that exists in _ENDPOINTS."""
        from pathlib import Path

        rws_path = Path(__file__).parent.parent / "src" / "abb_robot_client" / "rws.py"
        keys = self._extract_url_keys(str(rws_path))
        assert len(keys) > 30, f"Expected 30+ url() calls, found {len(keys)}"
        for key, lineno in keys:
            assert key in _ENDPOINTS, (
                f"rws.py:{lineno} — url({key!r}) not in _ENDPOINTS"
            )

    def test_rws_aio_url_keys_all_valid(self):
        """Every url() call in rws_aio.py must reference a key that exists in _ENDPOINTS."""
        from pathlib import Path

        aio_path = (
            Path(__file__).parent.parent / "src" / "abb_robot_client" / "rws_aio.py"
        )
        keys = self._extract_url_keys(str(aio_path))
        assert len(keys) > 30, f"Expected 30+ url() calls, found {len(keys)}"
        for key, lineno in keys:
            assert key in _ENDPOINTS, (
                f"rws_aio.py:{lineno} — url({key!r}) not in _ENDPOINTS"
            )

    def test_no_dead_endpoints(self):
        """Every _ENDPOINTS key should be referenced by at least one url() call.

        Dead entries accumulate silently and may contain stale URLs that were never
        validated against hardware.
        """
        from pathlib import Path

        base = Path(__file__).parent.parent / "src" / "abb_robot_client"
        all_keys = set()
        for f in ["rws.py", "rws_aio.py"]:
            all_keys.update(k for k, _ in self._extract_url_keys(str(base / f)))

        # These are documented as reserved for future API methods
        reserved = {"mastership_req", "mastership_rel", "load_program", "rmmp_cancel"}

        for endpoint_key in _ENDPOINTS:
            assert endpoint_key in all_keys or endpoint_key in reserved, (
                f"_ENDPOINTS[{endpoint_key!r}] is never referenced in url() calls "
                f"and is not in the reserved set"
            )


class TestDetectRobotwareVersion:
    """Test the version detection probe logic using mocked HTTP responses.

    detect_robotware_version makes two sequential HTTP requests to determine
    whether the controller speaks RWS1 (Digest auth) or RWS2 (Basic auth).
    """

    def test_rw7_detected_on_basic_200(self):
        """If Basic auth returns 200, controller is RW7."""
        from unittest.mock import patch, MagicMock
        from abb_robot_client.rws_profile import detect_robotware_version

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch(
            "abb_robot_client.rws_profile.requests.get", return_value=mock_resp
        ) as mock_get:
            result = detect_robotware_version("http://1.2.3.4", "user", "pass")

        assert result is RobotWareVersion.RW7
        mock_get.assert_called_once()

    def test_rw6_detected_on_basic_401_then_digest_200(self):
        """If Basic auth returns 401 and Digest returns 200, controller is RW6."""
        from unittest.mock import patch, MagicMock
        from abb_robot_client.rws_profile import detect_robotware_version

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_200 = MagicMock()
        resp_200.status_code = 200

        with patch(
            "abb_robot_client.rws_profile.requests.get",
            side_effect=[resp_401, resp_200],
        ) as mock_get:
            result = detect_robotware_version("http://1.2.3.4", "user", "pass")

        assert result is RobotWareVersion.RW6
        assert mock_get.call_count == 2

    def test_unexpected_status_raises(self):
        """If Basic auth returns non-200/non-401 (e.g. 403), raise immediately."""
        from unittest.mock import patch, MagicMock
        from abb_robot_client.rws_profile import detect_robotware_version

        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch("abb_robot_client.rws_profile.requests.get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="Unexpected HTTP 403"):
                detect_robotware_version("http://1.2.3.4", "user", "pass")

    def test_both_fail_raises(self):
        """If Basic returns 401 and Digest returns non-200, raise with status."""
        from unittest.mock import patch, MagicMock
        from abb_robot_client.rws_profile import detect_robotware_version

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_500 = MagicMock()
        resp_500.status_code = 500

        with patch(
            "abb_robot_client.rws_profile.requests.get",
            side_effect=[resp_401, resp_500],
        ):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                detect_robotware_version("http://1.2.3.4", "user", "pass")
