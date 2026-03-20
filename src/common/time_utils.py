from __future__ import annotations


def hhmmss_to_seconds(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid HH:MM:SS value: {value}")
    h, m, s = (int(p) for p in parts)
    return h * 3600 + m * 60 + s
