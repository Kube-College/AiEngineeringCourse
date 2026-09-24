#!/usr/bin/env python3
"""Run the opt-in local Docker qualification; never read GitHub credentials."""

import argparse
import os

from openhands_controller.config import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", required=True)
    args = parser.parse_args()
    if not args.smoke:
        return 2
    settings = Settings()
    if not settings.llm_api_key.get_secret_value():
        print("OpenRouter key unavailable; live smoke disabled")
        return 2
    image_digest = os.environ.get("OPENHANDS_IMAGE_DIGEST", "")
    if not image_digest.startswith("sha256:"):
        print("Pinned Agent Server image digest unavailable; live smoke disabled")
        return 2
    from openhands_controller.adapters.openhands import run_smoke

    return run_smoke(settings, image_digest)


if __name__ == "__main__":
    raise SystemExit(main())
