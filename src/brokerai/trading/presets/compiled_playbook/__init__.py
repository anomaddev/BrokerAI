from brokerai.trading.presets.compiled_playbook.signal import (
    CompiledPlaybookSignalEvaluator,
    register_compiled_playbook_signal,
)

__all__ = [
    "CompiledPlaybookSignalEvaluator",
    "register_compiled_playbook",
    "register_compiled_playbook_signal",
]


def register_compiled_playbook() -> None:
    register_compiled_playbook_signal()
