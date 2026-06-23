"""Orchestrator entry point: python -m brokerai.orchestrator"""

import asyncio

from brokerai.core.orchestrator import run_orchestrator


def main() -> None:
    asyncio.run(run_orchestrator())


if __name__ == "__main__":
    main()
