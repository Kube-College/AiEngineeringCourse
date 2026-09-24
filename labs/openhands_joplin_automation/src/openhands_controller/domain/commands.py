import re
from decimal import Decimal


_SIMPLE = re.compile(r"/agent (implement|pause|resume|cancel)")
_BUDGET = re.compile(r"/agent budget ([0-9]+(?:\.[0-9]{1,6})?)")


def parse_command(body: str) -> tuple[str, int | None] | None:
    """Accept one entire command, never quoted or embedded examples.

    A budget command carries its new total in microdollars.
    """
    command = body.strip()
    if match := _SIMPLE.fullmatch(command):
        return match.group(1), None
    if match := _BUDGET.fullmatch(command):
        total = int(Decimal(match.group(1)) * 1_000_000)
        return ("budget", total) if total > 0 else None
    return None
