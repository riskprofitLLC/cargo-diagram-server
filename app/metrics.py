"""Метрики (задачи 6.3/4.4): счётчики и gauge'и в памяти, /metrics в тексте Prometheus."""
import threading

_lock = threading.Lock()
_counts: dict[str, int] = {}
_gauges: dict[str, float] = {}


def inc(name: str, value: int = 1) -> None:
    with _lock:
        _counts[name] = _counts.get(name, 0) + value


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = value


def render() -> str:
    with _lock:
        lines = [f"{k} {v}\n" for k, v in sorted(_counts.items())]
        lines += [f"{k} {v:g}\n" for k, v in sorted(_gauges.items())]
        return "".join(lines)


def reset() -> None:
    """Сброс метрик (тесты)."""
    with _lock:
        _counts.clear()
        _gauges.clear()
