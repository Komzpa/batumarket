"""Helpers to adjust the OOM killer preference."""


def prefer_oom_kill(score: int = 1000) -> None:
    """Make this process the first OOM victim."""
    try:
        with open("/proc/self/oom_score_adj", "w", encoding="ascii") as fh:
            fh.write(f"{score}\n")
    except PermissionError as exc:
        raise SystemExit(
            "Need sudo or CAP_SYS_RESOURCE to set that value"
        ) from exc
    except OSError:
        # Read-only /proc inside restricted containers
        pass

