from __future__ import annotations

import io
import math
import unittest

from vkong_connect.contracts.events import EventSink, EventType, parse_event_line
from vkong_connect.errors import ContractError


class EventContractTests(unittest.TestCase):
    def test_sink_emits_monotonic_round_trippable_events(self) -> None:
        output = io.StringIO()
        sink = EventSink("job-1", output)

        first = sink.emit(EventType.PHASE, {"phase": "training"})
        second = sink.emit(EventType.METRIC, {"step": 1, "loss": math.nan})

        self.assertEqual(first.seq, 1)
        self.assertEqual(second.seq, 2)
        lines = output.getvalue().splitlines()
        self.assertEqual(parse_event_line(lines[0]), first)
        parsed_second = parse_event_line(lines[1])
        assert parsed_second is not None
        self.assertIsNone(parsed_second.payload["loss"])

    def test_ordinary_log_line_is_ignored(self) -> None:
        self.assertIsNone(parse_event_line("Downloading model"))

    def test_malformed_prefixed_line_fails_closed(self) -> None:
        with self.assertRaises(ContractError):
            parse_event_line("VKONG_EVENT not-json")

    def test_coercible_but_invalid_contract_types_fail_closed(self) -> None:
        template = (
            'VKONG_EVENT {"v":1,"job_id":"job-1","seq":%s,'
            '"time":"2026-09-20T10:00:00Z","type":"metric","payload":{}}'
        )
        for invalid_sequence in ('"1"', "true"):
            with self.subTest(seq=invalid_sequence), self.assertRaises(ContractError):
                parse_event_line(template % invalid_sequence)


if __name__ == "__main__":
    unittest.main()
