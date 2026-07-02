import logging
import subprocess
import sys
from typing import List, Tuple

from utils.constants import APP_NAME, PEER_DISCOVERY_PORT

logger = logging.getLogger(__name__)

RULE_NAME_DISCOVERY: str = f"{APP_NAME} - Discovery (UDP {PEER_DISCOVERY_PORT})"
RULE_NAME_DATA: str = f"{APP_NAME} - Data (TCP)"


def _run_netsh(args: List[str]) -> Tuple[bool, str]:
    if sys.platform != "win32":
        return False, "not Windows"
    try:
        cmd: List[str] = ["netsh", "advfirewall", "firewall"] + args
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.debug(f"Firewall rule OK: {' '.join(args[:4])}")
            return True, ""
        else:
            msg: str = result.stderr.strip() or result.stdout.strip() or "unknown error"
            logger.warning(f"Firewall rule failed: {msg}")
            return False, msg
    except FileNotFoundError:
        logger.debug("netsh not found, cannot configure firewall")
        return False, "netsh not found"
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug(f"Cannot configure firewall: {e}")
        return False, str(e)


def rule_exists(name: str) -> bool:
    ok, _ = _run_netsh(["show", "rule", f"name={name}"])
    return ok


def add_discovery_rule() -> Tuple[bool, str]:
    if sys.platform != "win32":
        return False, "not Windows"
    if rule_exists(RULE_NAME_DISCOVERY):
        logger.info(f"Firewall rule already exists: {RULE_NAME_DISCOVERY}")
        return True, ""
    logger.info(f"Adding firewall rule: {RULE_NAME_DISCOVERY}")
    return _run_netsh([
        "add", "rule",
        f"name={RULE_NAME_DISCOVERY}",
        "dir=in",
        "action=allow",
        f"protocol=udp",
        f"localport={PEER_DISCOVERY_PORT}",
        "description=SecureP2P peer discovery via UDP multicast"
    ])


def add_data_rule(port: int = 0) -> Tuple[bool, str]:
    if sys.platform != "win32":
        return False, "not Windows"
    if rule_exists(RULE_NAME_DATA):
        logger.info(f"Firewall rule already exists: {RULE_NAME_DATA}")
        return True, ""
    if port:
        logger.info(f"Adding firewall rule: {RULE_NAME_DATA} (TCP {port})")
        return _run_netsh([
            "add", "rule",
            f"name={RULE_NAME_DATA}",
            "dir=in",
            "action=allow",
            "protocol=tcp",
            f"localport={port}",
            "description=SecureP2P encrypted data transfer"
        ])
    logger.info(f"Adding firewall rule: {RULE_NAME_DATA} (TCP dynamic)")
    return _run_netsh([
        "add", "rule",
        f"name={RULE_NAME_DATA}",
        "dir=in",
        "action=allow",
        "protocol=tcp",
        "description=SecureP2P encrypted data transfer"
    ])


def remove_rules() -> bool:
    if sys.platform != "win32":
        return False
    ok: bool = True
    for name in (RULE_NAME_DISCOVERY, RULE_NAME_DATA):
        success, _ = _run_netsh(["delete", "rule", f"name={name}"])
        if not success:
            ok = False
    return ok


def configure_firewall(server_port: int = 0) -> Tuple[bool, str]:
    disc_ok, disc_msg = add_discovery_rule()
    data_ok, data_msg = add_data_rule(server_port)
    if disc_ok and data_ok:
        return True, "Firewall rules configured"
    errors: List[str] = []
    if not disc_ok:
        errors.append(f"Discovery: {disc_msg}")
    if not data_ok:
        errors.append(f"Data: {data_msg}")
    return False, "; ".join(errors)
