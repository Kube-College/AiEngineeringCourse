import re


_SIMPLE = re.compile(r"/agent (implement|pause|resume|cancel)")
_BUDGET = re.compile(r"/agent budget ([0-9]+(?:\.[0-9]{1,6})?)")


def parse_command(body: str) -> tuple[str, str | None] | None:
    """Accept one entire command, never quoted or embedded examples."""
    command = body.strip()
    match = _SIMPLE.fullmatch(command)
    if match:
        return match.group(1), None
    match = _BUDGET.fullmatch(command)
    if match:
        return "budget", match.group(1)
    return None
