"""Lightweight mock-session diagnostics, including monitor overhead in the totals."""
from datetime import datetime
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Qt


def resident_bytes():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged', 'paged',
                    'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        query = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        if query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.working
    elif Path('/proc/self/statm').exists():
        return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    return None


class SessionMetrics(QObject):
    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.started = self.previous_beat = self.previous_sample = time.perf_counter()
        self.started_cpu = self.previous_cpu = time.process_time()
        self.current_rss = resident_bytes()
        self.start_rss = self.peak_rss = self.current_rss
        self.ticks = 0; self.max_gap = 0; self.gaps_over_100ms = 0
        self.gaps_by_phase = {}
        self.cpu_percent = 0
        self.heartbeat = QTimer(self)
        self.heartbeat.setTimerType(Qt.TimerType.PreciseTimer)
        self.heartbeat.setInterval(20); self.heartbeat.timeout.connect(self._beat)
        self.sampler = QTimer(self)
        self.sampler.setInterval(500); self.sampler.timeout.connect(self._sample)
        self.heartbeat.start(); self.sampler.start()
        self._sample()

    def _beat(self):
        now = time.perf_counter()
        gap = now - self.previous_beat
        self.previous_beat = now; self.ticks += 1
        self.max_gap = max(self.max_gap, gap)
        self.gaps_over_100ms += gap > .1
        phase = self.bridge.phase
        self.gaps_by_phase[phase] = max(self.gaps_by_phase.get(phase, 0), gap)

    def _sample(self):
        now = time.perf_counter(); cpu = time.process_time()
        duration = now - self.previous_sample
        self.cpu_percent = 100 * (cpu - self.previous_cpu) / max(duration, .001) / (os.cpu_count() or 1)
        self.previous_sample = now; self.previous_cpu = cpu
        self.current_rss = resident_bytes()
        if self.current_rss is not None:
            self.peak_rss = max(self.peak_rss or 0, self.current_rss)
        memory = f'{self.current_rss / 1048576:.0f} MiB' if self.current_rss is not None else 'unavailable'
        self.bridge.update_diagnostics(f'RAM {memory} · CPU {self.cpu_percent:.1f}% · Max UI gap {self.max_gap * 1000:.0f} ms')

    def snapshot(self):
        self._sample()
        elapsed = time.perf_counter() - self.started
        cpu_seconds = time.process_time() - self.started_cpu
        mib = lambda value: round(value / 1048576, 2) if value is not None else None
        return dict(mode='offline_mock', elapsed_seconds=round(elapsed, 3),
                    process_cpu_seconds=round(cpu_seconds, 3), logical_cpus=os.cpu_count(),
                    average_cpu_percent=round(100 * cpu_seconds / max(elapsed, .001) / (os.cpu_count() or 1), 2),
                    initial_rss_mib=mib(self.start_rss), current_rss_mib=mib(self.current_rss),
                    peak_rss_mib=mib(self.peak_rss), ui_heartbeat_interval_ms=20,
                    ui_heartbeat_ticks=self.ticks, max_ui_gap_ms=round(self.max_gap * 1000, 2),
                    ui_gaps_over_100ms=self.gaps_over_100ms,
                    max_ui_gap_by_phase_ms={phase: round(gap * 1000, 2) for phase, gap in self.gaps_by_phase.items()},
                    counts={key: getattr(self.bridge, key) for key in ('total', 'processed', 'completed', 'skipped', 'failed')},
                    last_export=self.bridge.lastOutput,
                    notes='Monitoring begins after QML load and before its first frame. Includes rendering, workbook import at Start, SQLite, collection, export and monitor overhead; excludes Python imports and mock input generation. RAM peak is the largest sampled working set. CPU is normalized across logical CPUs. UI gap is timer delivery interval, not GPU frame time; phase labels are approximate at transitions. Minimized/background windows may be throttled. No browser/network/CAPTCHA cost is measured.')

    def save_report(self, folder):
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'mock-performance-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.json'
        path.write_text(json.dumps(self.snapshot(), indent=2) + '\n', encoding='utf-8')
        return path

    def stop(self):
        self.heartbeat.stop(); self.sampler.stop()
