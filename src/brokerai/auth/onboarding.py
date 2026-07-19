"""Persisted first-run onboarding progress (post-admin wizard steps).

Stores a small JSON document under the auth data directory so the web UI can
resume mid-wizard after refresh or re-login. Completing onboarding does not
start bots in this phase — that is deferred to a later release.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from brokerai.config.settings import Settings, get_settings

ONBOARDING_FILE = "onboarding.json"

OnboardingStep = Literal["admin", "exchange", "instruments", "data_sources", "models", "finish"]

ONBOARDING_STEPS: tuple[OnboardingStep, ...] = (
    "admin",
    "exchange",
    "instruments",
    "data_sources",
    "models",
    "finish",
)

_POST_ADMIN_STEPS = frozenset({"exchange", "instruments", "data_sources", "models", "finish"})


def _normalize_step(step_raw: str) -> OnboardingStep:
    """Map persisted/legacy step ids onto the current wizard."""
    if step_raw == "strategy":
        return "data_sources"
    if step_raw in ONBOARDING_STEPS:
        return step_raw  # type: ignore[return-value]
    return "admin"


@dataclass
class OnboardingState:
    current_step: OnboardingStep
    complete: bool
    selected_exchange_id: str | None = None
    enabled_pairs: list[str] | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "current_step": self.current_step,
            "complete": self.complete,
        }
        if self.selected_exchange_id:
            payload["selected_exchange_id"] = self.selected_exchange_id
        if self.enabled_pairs is not None:
            payload["enabled_pairs"] = list(self.enabled_pairs)
        if self.strategy_id:
            payload["strategy_id"] = self.strategy_id
        if self.strategy_name:
            payload["strategy_name"] = self.strategy_name
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> OnboardingState:
        step = _normalize_step(str(data.get("current_step") or "admin"))
        pairs = data.get("enabled_pairs")
        enabled_pairs: list[str] | None = None
        if isinstance(pairs, list):
            enabled_pairs = [str(p) for p in pairs if isinstance(p, str)]
        return cls(
            current_step=step,
            complete=bool(data.get("complete")),
            selected_exchange_id=str(data["selected_exchange_id"])
            if data.get("selected_exchange_id")
            else None,
            enabled_pairs=enabled_pairs,
            strategy_id=str(data["strategy_id"]) if data.get("strategy_id") else None,
            strategy_name=str(data["strategy_name"]) if data.get("strategy_name") else None,
        )


class OnboardingStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = self.settings.auth_dir / ONBOARDING_FILE

    def ensure_dir(self) -> None:
        self.settings.auth_dir.mkdir(parents=True, exist_ok=True)

    def _read(self) -> OnboardingState | None:
        if self.settings.use_postgres:
            try:
                from brokerai.auth.pg_profile import load_onboarding

                data = load_onboarding()
                if data is not None:
                    return OnboardingState.from_dict(data)
            except Exception:
                pass
        if not self.path.exists():
            return None
        try:
            return OnboardingState.from_dict(json.loads(self.path.read_text()))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return None

    def _write(self, state: OnboardingState) -> OnboardingState:
        self.ensure_dir()
        payload = state.to_dict()
        self.path.write_text(json.dumps(payload, indent=2))
        if self.settings.use_postgres:
            try:
                from brokerai.auth.pg_profile import save_onboarding

                save_onboarding(payload)
            except Exception:
                pass
        return state

    def get_state(self) -> OnboardingState:
        existing = self._read()
        if existing is not None:
            return existing
        return OnboardingState(current_step="admin", complete=False)

    def is_complete(self) -> bool:
        state = self._read()
        return bool(state and state.complete)

    def init_after_admin(self) -> OnboardingState:
        """Seed progress after the admin account exists (first wizard resume point)."""
        existing = self._read()
        if existing is not None and existing.complete:
            return existing
        if existing is not None and existing.current_step != "admin":
            return existing
        return self._write(
            OnboardingState(
                current_step="exchange",
                complete=False,
                selected_exchange_id=existing.selected_exchange_id if existing else None,
                enabled_pairs=existing.enabled_pairs if existing else None,
                strategy_id=existing.strategy_id if existing else None,
                strategy_name=existing.strategy_name if existing else None,
            )
        )

    def update_progress(
        self,
        *,
        current_step: OnboardingStep | None = None,
        selected_exchange_id: str | None = None,
        enabled_pairs: list[str] | None = None,
        strategy_id: str | None = None,
        strategy_name: str | None = None,
        clear_selected_exchange: bool = False,
    ) -> OnboardingState:
        state = self.get_state()
        if state.complete:
            raise ValueError("Onboarding already complete")

        step = current_step or state.current_step
        if step not in ONBOARDING_STEPS:
            raise ValueError(f"Unknown onboarding step: {step}")
        if step == "admin":
            raise ValueError("Cannot set progress back to admin via API")

        exchange_id = state.selected_exchange_id
        if clear_selected_exchange:
            exchange_id = None
        elif selected_exchange_id is not None:
            exchange_id = selected_exchange_id.strip() or None

        pairs = state.enabled_pairs
        if enabled_pairs is not None:
            pairs = list(enabled_pairs)

        sid = state.strategy_id
        if strategy_id is not None:
            sid = strategy_id.strip() or None
        sname = state.strategy_name
        if strategy_name is not None:
            sname = strategy_name.strip() or None

        return self._write(
            OnboardingState(
                current_step=step,  # type: ignore[arg-type]
                complete=False,
                selected_exchange_id=exchange_id,
                enabled_pairs=pairs,
                strategy_id=sid,
                strategy_name=sname,
            )
        )

    def mark_complete(self) -> OnboardingState:
        state = self.get_state()
        return self._write(
            OnboardingState(
                current_step="finish",
                complete=True,
                selected_exchange_id=state.selected_exchange_id,
                enabled_pairs=state.enabled_pairs,
                strategy_id=state.strategy_id,
                strategy_name=state.strategy_name,
            )
        )

    def reset(self) -> None:
        """Remove onboarding progress (used by local design harness)."""
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        if self.settings.use_postgres:
            try:
                from brokerai.auth.pg_profile import delete_onboarding

                delete_onboarding()
            except Exception:
                pass


def resolve_onboarding_status(*, auth_complete: bool) -> dict[str, object]:
    """Build the public/status payload for AuthGate and the wizard shell.

    Legacy installs that already have an admin but no ``onboarding.json`` are
    treated as complete so existing deployments are not forced back through
    the wizard. New admins always get an onboarding file via ``init_after_admin``.
    """
    store = OnboardingStore()
    if not auth_complete:
        return {
            "auth_complete": False,
            "onboarding_complete": False,
            "current_step": "admin",
            "selected_exchange_id": None,
            "enabled_pairs": None,
            "strategy_id": None,
            "strategy_name": None,
        }

    existing = store._read()
    if existing is None:
        # Pre-onboarding install: admin exists, never started the new wizard.
        return {
            "auth_complete": True,
            "onboarding_complete": True,
            "current_step": "finish",
            "selected_exchange_id": None,
            "enabled_pairs": None,
            "strategy_id": None,
            "strategy_name": None,
        }

    if existing.complete:
        return {
            "auth_complete": True,
            "onboarding_complete": True,
            "current_step": "finish",
            "selected_exchange_id": existing.selected_exchange_id,
            "enabled_pairs": existing.enabled_pairs,
            "strategy_id": existing.strategy_id,
            "strategy_name": existing.strategy_name,
        }

    step: OnboardingStep = existing.current_step
    if step == "admin" or step not in _POST_ADMIN_STEPS:
        store.init_after_admin()
        existing = store.get_state()

    return {
        "auth_complete": True,
        "onboarding_complete": False,
        "current_step": existing.current_step if existing.current_step != "admin" else "exchange",
        "selected_exchange_id": existing.selected_exchange_id,
        "enabled_pairs": existing.enabled_pairs,
        "strategy_id": existing.strategy_id,
        "strategy_name": existing.strategy_name,
    }


def onboarding_path(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return s.auth_dir / ONBOARDING_FILE
