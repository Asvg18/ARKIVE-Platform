"""Tests for who the API thinks a request came from, once a proxy is in
front of it.

Both unauthenticated endpoints are rate limited per visitor, and both
identify a visitor by `request.client.host`. In development that is the
browser's real address, because nothing sits between them. In the
deployed stack Caddy does, so uvicorn has to be told to read the real
address out of X-Forwarded-For -- and told *whose* copy of that header
it is allowed to believe.

Left at its default (trust only 127.0.0.1) the header is ignored and
every request looks like it came from Caddy. Two live consequences, both
silent:

  * the signup cap -- 10 accounts per visitor per hour -- becomes 10 for
    the whole system, so the 11th applicant of a hiring drive is turned
    away with nothing in the logs to say why;
  * the login lockout is keyed on email *and* address precisely so that
    nobody can lock out a known user on purpose. With the address half
    constant, that is exactly what it becomes.

Worth testing rather than trusting to a config line, because the failure
appears in neither place anyone looks: development has no proxy, and the
test client talks to the app directly. Only the deployment is affected.

The first half exercises uvicorn's own trust logic with the value the
deployment actually passes, so it tests the security property rather
than a string. The second half checks that value is really wired
through, since a correct setting in an unread file protects nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from uvicorn.middleware.proxy_headers import _TrustedHosts

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"
ENTRYPOINT = REPO_ROOT / "backend" / "docker-entrypoint.sh"

# A stand-in for Caddy's address inside the compose network, and for a
# real visitor arriving from the university LAN.
PROXY_ADDRESS = "172.28.0.5"
REAL_VISITOR = "192.168.1.77"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


def _configured_trust() -> str:
    """The FORWARDED_ALLOW_IPS default baked into the compose file."""
    raw = _compose()["services"]["backend"]["environment"]["FORWARDED_ALLOW_IPS"]
    # "${FORWARDED_ALLOW_IPS:-172.28.0.0/24}" -> "172.28.0.0/24"
    match = re.fullmatch(r"\$\{FORWARDED_ALLOW_IPS:-(?P<default>[^}]+)\}", raw)
    assert match, f"Could not read a default out of {raw!r}"
    return match.group("default")


# --------------------------------------------------------------------
# What the setting actually buys, exercised against uvicorn's own logic
# --------------------------------------------------------------------


def test_the_default_setting_cannot_see_past_the_proxy():
    """The bug, pinned. Out of the box uvicorn trusts only 127.0.0.1, and
    Caddy runs in its own container -- so the header is discarded and
    every visitor is indistinguishable from every other."""
    assert PROXY_ADDRESS not in _TrustedHosts("127.0.0.1")


def test_the_configured_network_sees_the_real_visitor():
    hosts = _TrustedHosts(_configured_trust())
    assert PROXY_ADDRESS in hosts, "the proxy's own address must be trusted"
    host, _port = hosts.get_trusted_client_address(REAL_VISITOR)
    assert host == REAL_VISITOR


def test_a_forged_forwarded_header_does_not_win():
    """A caller can type anything into X-Forwarded-For. Caddy appends the
    address it actually saw, so the list arrives as "<forged>, <real>";
    uvicorn reads from the right and takes the first address outside the
    trusted network, which is the real one."""
    hosts = _TrustedHosts(_configured_trust())
    host, _port = hosts.get_trusted_client_address(f"1.2.3.4, {REAL_VISITOR}")
    assert host == REAL_VISITOR


def test_trusting_everything_would_hand_the_attacker_the_pen():
    """Why the setting is a network and never "*".

    With "*" uvicorn stops walking the list and takes the *first* entry
    -- the one the caller supplies. An attacker would then mint a fresh
    identity per request and neither rate limit would ever trigger. This
    is the alternative that looks simpler and quietly removes the
    protection entirely, so it is pinned here rather than left to a
    comment."""
    host, _port = _TrustedHosts("*").get_trusted_client_address(f"1.2.3.4, {REAL_VISITOR}")
    assert host == "1.2.3.4"


def test_a_visitor_on_a_private_lan_is_still_told_apart():
    """Why the trusted set is this stack's own pinned /24 rather than the
    whole 172.16.0.0/12 private range: a university LAN can live inside
    that range too, and then a real visitor's address would be treated as
    another hop and skipped, handing the forged entry the result."""
    hosts = _TrustedHosts(_configured_trust())
    lan_visitor = "172.20.5.5"
    host, _port = hosts.get_trusted_client_address(f"1.2.3.4, {lan_visitor}")
    assert host == lan_visitor


# --------------------------------------------------------------------
# That the setting is really wired through
# --------------------------------------------------------------------


def test_the_api_is_started_with_the_flag():
    assert "--forwarded-allow-ips" in ENTRYPOINT.read_text()


def test_the_flag_reads_the_environment_variable_the_deployment_sets():
    assert "FORWARDED_ALLOW_IPS" in ENTRYPOINT.read_text()


def test_the_deployment_never_trusts_everything():
    assert _configured_trust() != "*"


def test_the_trusted_network_matches_the_network_the_stack_runs_on():
    """The subnet is written in two places -- the network definition and
    the value the backend trusts -- and nothing but this test stops them
    drifting apart. They are far enough apart in the file to be edited
    separately."""
    subnet = _compose()["networks"]["default"]["ipam"]["config"][0]["subnet"]
    assert _configured_trust() == subnet
