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
        assert RW6_PROFILE.headers == {}

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
