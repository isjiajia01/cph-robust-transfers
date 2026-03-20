from __future__ import annotations

"""Bridge entry points for the accessibility product slice."""


def accessibility_server_main():
    from src.accessibility.server import main

    return main(["serve"])


def accessibility_build_static_main():
    from src.accessibility.server import main

    return main(["build-static"])


__all__ = [
    "accessibility_server_main",
    "accessibility_build_static_main",
]
