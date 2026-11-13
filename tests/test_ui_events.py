import unittest
from al_results.events import EventBuffer
from al_results.models import WorkerEvent


class UIEventTests(unittest.TestCase):
    def test_bounded_snapshots_and_reliable_terminal_events(self):
        buffer = EventBuffer()
        for i in range(2000):
            buffer.put(WorkerEvent('progress', {'processed': i}))
            buffer.put(WorkerEvent('log', {'text': str(i)}))
        buffer.put(WorkerEvent('fatal', {'error': 'Example'}))
        events = buffer.drain()
        self.assertEqual(len(events), 502)
        self.assertEqual(events[0].payload['processed'], 1999)
        self.assertEqual(events[-1].kind, 'fatal')
        self.assertEqual(buffer.drain(), [])
