"""Policy loading.

Law 6: the guard cannot be talked out of it. Limits live in this file on disk,
loaded once at startup and checksummed. There is deliberately no setter, no
tool and no natural-language path that changes a threshold at runtime; the only
way to change one is to edit the file and restart. The SHA-256 travels into
every receipt so a reader can tell which rules produced a given decision.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "policy.yaml"


class PolicyError(RuntimeError):
    """Raised loudly. A guard running on unreadable policy is not a guard."""


@dataclass(frozen=True)
class Policy:
    raw: dict[str, Any]
    sha256: str
    path: Path

    # --- accessors; every threshold is read through one of these ---

    @property
    def status(self) -> str:
        return str(self.raw["status"])

    @property
    def is_calibrated(self) -> bool:
        return self.status == "CALIBRATED"

    @property
    def base_notional(self) -> float:
        return float(self.raw["base_notional_usdt"])

    @property
    def min_rth_samples(self) -> int:
        return int(self.raw["calibration"]["min_rth_samples"])

    @property
    def baseline_window_days(self) -> float:
        return float(self.raw["calibration"]["baseline_window_days"])

    @property
    def walk_cost_cap_bps(self) -> float:
        return float(self.raw["liquidity"]["walk_cost_cap_bps"])

    @property
    def depth_band_pct(self) -> float:
        return float(self.raw["liquidity"]["depth_band_pct"])

    @property
    def liquidity_tiers(self) -> list[dict[str, float]]:
        return list(self.raw["liquidity"]["tiers"])

    @property
    def liquidity_otherwise(self) -> float:
        return float(self.raw["liquidity"]["otherwise_factor"])

    @property
    def clock_factors(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw["clock"]["factors"].items()}

    @property
    def ramp_start_minutes(self) -> float:
        return float(self.raw["clock"]["ramp_start_minutes_to_close"])

    @property
    def backward_gap(self) -> list[dict]:
        return list(self.raw["clock"]["backward_gap"])

    @property
    def forward_gap(self) -> list[dict]:
        return list(self.raw["clock"]["forward_gap"])

    @property
    def basis_bands(self) -> dict[str, dict[str, Any]]:
        return dict(self.raw["basis"]["bands"])

    @property
    def degraded_floor_reference_age_s(self) -> float:
        return float(self.raw["basis"]["degraded_floor_reference_age_s"])

    @property
    def max_reference_age_s(self) -> float:
        return float(self.raw["basis"]["max_reference_age_s"])

    @property
    def tradable_statuses(self) -> set[str]:
        return {str(x).upper()
                for x in self.raw["corporate_actions"]["tradable_statuses"]}

    @property
    def ramp_floor(self) -> float:
        return float(self.raw["clock"]["ramp_floor"])

    @property
    def corp_action_lookahead_h(self) -> float:
        return float(self.raw["corporate_actions"]["lookahead_hours"])

    @property
    def registry_sha256(self) -> str:
        return str(self.raw["registry_sha256"])

    # --- execution ceilings; all of them cap, none of them permit ---

    @property
    def executor_enabled(self) -> bool:
        return bool(self.raw.get("executor", {}).get("enabled", False))

    @property
    def executor_max_order_usdt(self) -> float:
        return float(self.raw.get("executor", {}).get("max_order_usdt", 0.0))

    @property
    def executor_symbols(self) -> set[str]:
        return {str(x).upper()
                for x in self.raw.get("executor", {}).get("symbols", [])}

    @property
    def executor_requires_manual(self) -> bool:
        return bool(self.raw.get("executor", {})
                    .get("require_manual_invocation", True))

    @property
    def exposure_max_gross_usdt(self) -> float:
        return float(self.raw.get("exposure", {})
                     .get("max_gross_usdt", 0.0))

    @property
    def exposure_snapshot_max_age_s(self) -> float:
        return float(self.raw.get("exposure", {})
                     .get("snapshot_max_age_s", 0.0))

    @property
    def exposure_position_public_key(self) -> Path:
        configured = str(self.raw.get("exposure", {})
                         .get("position_public_key", "")).strip()
        path = Path(configured)
        return path if path.is_absolute() else self.path.parent / path

    @property
    def exposure_requires_snapshot(self) -> bool:
        return bool(self.raw.get("exposure", {})
                    .get("require_snapshot", False))

    @property
    def kill_file(self) -> Path:
        return Path(str(self.raw["operator_freeze"]["kill_file"]))

    def freeze_active(self) -> bool:
        """True when the operator freeze file is present.

        An unreadable path fails closed. A freeze whose state cannot be read is
        treated as engaged, because the failure mode of a freeze that silently
        stops working is the one that matters.
        """
        try:
            return self.kill_file.exists()
        except OSError:
            return True


_REQUIRED = ("version", "status", "base_notional_usdt", "calibration", "clock",
             "liquidity", "basis", "corporate_actions", "registry_sha256",
             "verdicts", "operator_freeze", "exposure")


def load(path: str | Path | None = None) -> Policy:
    """Load, validate and checksum the policy. Every failure raises."""
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        raise PolicyError(f"policy file not found: {p}")
    data = p.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    try:
        raw = yaml.safe_load(data.decode())
    except yaml.YAMLError as exc:
        raise PolicyError(f"policy is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyError("policy must be a mapping")

    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise PolicyError(f"policy missing required keys: {missing}")

    pol = Policy(raw, digest, p)

    # A registry the policy does not recognise is a hard failure: it means the
    # canonical contract set changed without the policy being reviewed (P6).
    from afterbell.instruments import registry_sha256
    if pol.registry_sha256 != registry_sha256():
        raise PolicyError(
            "canonical registry checksum does not match the policy. Expected "
            f"{pol.registry_sha256}, computed {registry_sha256()}. Refusing to "
            "run: the instrument set changed without policy review.")

    # Law 7: the declared action space must stay risk-reducing.
    verdicts = set(raw["verdicts"])
    if verdicts != {"PASS", "WARN", "REDUCE", "BLOCK"}:
        raise PolicyError(f"verdict set must be exactly PASS/WARN/REDUCE/BLOCK, got {verdicts}")

    # Law 3: every market state must have a chosen factor. A state that falls
    # through to a default is a state nobody sized.
    from afterbell.clock import MarketState
    missing = [s.value for s in MarketState if s.value not in pol.clock_factors]
    if missing:
        raise PolicyError(f"policy has no clock factor for states: {missing}")

    try:
        window_days = pol.baseline_window_days
    except (TypeError, ValueError) as exc:
        raise PolicyError("calibration baseline_window_days must be numeric") from exc
    if not math.isfinite(window_days) or window_days <= 0:
        raise PolicyError(
            "calibration baseline_window_days must be a finite positive number")

    # The executor's ceiling must be a ceiling. A cap at or above the base
    # notional caps nothing, and a cap that is absent while execution is
    # enabled is the "|| 0" this project exists to argue against (Law 3).
    if "executor" in raw:
        cap = pol.executor_max_order_usdt
        if pol.executor_enabled:
            if cap <= 0:
                raise PolicyError(
                    "executor is enabled with max_order_usdt "
                    f"{cap}; a non-positive cap is not a cap")
            if cap > pol.base_notional:
                raise PolicyError(
                    f"executor max_order_usdt {cap} exceeds base_notional "
                    f"{pol.base_notional}; the execution ceiling may never be "
                    "looser than the sizing it is capping (Law 7)")
            if not pol.executor_symbols:
                raise PolicyError(
                    "executor is enabled with an empty symbol allowlist; an "
                    "empty allowlist must block everything, and silently "
                    "trading nothing is not what an operator would expect")

    # P7 is an account-wide ceiling, so it is not allowed to disappear just
    # Every policy carries explicit D5 limits. Read-only operation may leave
    # the input requirement off while the supported-client position source is
    # being configured; enabling execution may not.
    try:
        max_gross = pol.exposure_max_gross_usdt
        max_age = pol.exposure_snapshot_max_age_s
    except (TypeError, ValueError) as exc:
        raise PolicyError("exposure limits must be numeric") from exc
    if not math.isfinite(max_gross) or max_gross <= 0:
        raise PolicyError(
            "exposure max_gross_usdt must be a finite positive number")
    if not math.isfinite(max_age) or max_age <= 0:
        raise PolicyError(
            "exposure snapshot_max_age_s must be a finite positive number")
    if pol.executor_enabled and not pol.exposure_requires_snapshot:
        raise PolicyError(
            "executor is enabled while exposure.require_snapshot is false; "
            "an executable policy must require a verified position snapshot")
    if pol.executor_enabled and not pol.exposure_position_public_key.exists():
        raise PolicyError(
            "executor is enabled but the exposure position public key is "
            f"missing: {pol.exposure_position_public_key}")

    for name, factor in pol.clock_factors.items():
        if not 0.0 <= factor <= 1.0:
            raise PolicyError(
                f"clock factor {name}={factor} outside [0,1]; a factor above 1 "
                "would increase exposure, which the guard may never do (Law 7)")
    return pol
