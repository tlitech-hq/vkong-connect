"""Canonical, line-oriented training event contract."""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import IO, Any

from vkong_connect.errors import ContractError

EVENT_PREFIX = "VKONG_EVENT "
EVENT_VERSION = 1


class EventType(str, Enum):
    PHASE = "phase"
    MESSAGE = "message"
    WARNING = "warning"
    METRIC = "metric"
    CHECKPOINT = "checkpoint"
    ARTIFACT = "artifact"
    TERMINAL = "terminal"


def _clean_json(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    return value


@dataclass(frozen=True)
class BridgeEvent:
    job_id: str
    seq: int
    type: EventType
    payload: dict[str, Any]
    time: str
    version: int = EVENT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, str) or not self.job_id:
            raise ContractError("event job_id must not be empty")
        if not isinstance(self.seq, int) or isinstance(self.seq, bool) or self.seq < 1:
            raise ContractError("event seq must be at least 1")
        if (
            not isinstance(self.version, int)
            or isinstance(self.version, bool)
            or self.version != EVENT_VERSION
        ):
            raise ContractError(f"unsupported event version: {self.version}")
        if not isinstance(self.type, EventType):
            raise ContractError("event type must be an EventType")
        if not isinstance(self.payload, dict):
            raise ContractError("event payload must be an object")
        if not isinstance(self.time, str):
            raise ContractError("event time must be an RFC 3339 string")
        try:
            parsed_time = datetime.fromisoformat(self.time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError("event time must be an RFC 3339 string") from exc
        if parsed_time.tzinfo is None:
            raise ContractError("event time must include a timezone")

    def as_dict(self) -> dict[str, Any]:
        return {
            "v": self.version,
            "job_id": self.job_id,
            "seq": self.seq,
            "time": self.time,
            "type": self.type.value,
            "payload": _clean_json(self.payload),
        }

    def to_line(self) -> str:
        return EVENT_PREFIX + json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BridgeEvent":
        required = {"v", "job_id", "seq", "time", "type", "payload"}
        missing = required.difference(value)
        if missing:
            raise ContractError(f"event is missing fields: {', '.join(sorted(missing))}")
        try:
            event_type = EventType(value["type"])
        except (TypeError, ValueError) as exc:
            raise ContractError(f"unsupported event type: {value['type']!r}") from exc
        if not isinstance(value["payload"], dict):
            raise ContractError("event payload must be an object")
        return cls(
            version=value["v"],
            job_id=value["job_id"],
            seq=value["seq"],
            time=value["time"],
            type=event_type,
            payload=value["payload"],
        )


def parse_event_line(line: str) -> BridgeEvent | None:
    """Parse one runner line, returning None for an ordinary log line."""
    if not line.startswith(EVENT_PREFIX):
        return None
    try:
        value = json.loads(line[len(EVENT_PREFIX) :])
    except json.JSONDecodeError as exc:
        raise ContractError("invalid bridge event JSON") from exc
    if not isinstance(value, dict):
        raise ContractError("bridge event must be a JSON object")
    return BridgeEvent.from_dict(value)


class EventSink:
    """Thread-safe writer assigning one monotonic sequence per process."""

    def __init__(self, job_id: str, stream: IO[str]) -> None:
        if not job_id:
            raise ContractError("job_id must not be empty")
        self.job_id = job_id
        self.stream = stream
        self._seq = 0
        self._lock = threading.Lock()

    @property
    def last_sequence(self) -> int:
        with self._lock:
            return self._seq

    def emit(self, event_type: EventType | str, payload: dict[str, Any]) -> BridgeEvent:
        try:
            normalized_type = EventType(event_type)
        except ValueError as exc:
            raise ContractError(f"unsupported event type: {event_type!r}") from exc
        with self._lock:
            self._seq += 1
            event = BridgeEvent(
                job_id=self.job_id,
                seq=self._seq,
                type=normalized_type,
                payload=_clean_json(payload),
                time=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            self.stream.write(event.to_line() + "\n")
            self.stream.flush()
            return event
