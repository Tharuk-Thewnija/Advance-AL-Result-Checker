"""Small spike checks and visible-frame-aware timings, not production tests."""
from collections import deque
import statistics
import time
from PySide6.QtCore import QEventLoop, qVersion
from PySide6 import __version__ as pyside_version


def exercise(app, bridge, window, started, benchmark=False):
    frames = deque(maxlen=1000)
    window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))

    def pump(seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
            time.sleep(0.001)

    def paint_after(action, seconds=5):
        before = len(frames)
        cpu = time.process_time()
        wall = time.perf_counter()
        action()
        window.requestUpdate()
        deadline = wall + seconds
        while len(frames) <= before and time.perf_counter() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
            time.sleep(0.001)
        if len(frames) <= before:
            raise RuntimeError('Timed out waiting for a presented Qt Quick frame')
        return {'wall_ms': round((time.perf_counter() - wall) * 1000, 2),
                'cpu_ms': round((time.process_time() - cpu) * 1000, 2)}

    paint_after(lambda: None)
    first_frame_ms = round((time.perf_counter() - started) * 1000, 2)
    pump(.3)
    assert bridge.filtered.rowCount() == 63
    bridge.search('01'); assert bridge.filtered.rowCount() == 1
    bridge.search('communication technology'); assert bridge.filtered.rowCount() == 1
    bridge.selectSubject('01', True)
    bridge.search(''); assert bridge.selectedCount == 2
    bridge.clearSubjects(); assert bridge.selectedCount == 0
    bridge.selectSubject('20', True)
    for theme in ('Light', 'Dark', 'System'):
        paint_after(lambda theme=theme: setattr(bridge, 'theme', theme))
    bridge.startDemo(); pump(.1)
    assert bridge.processed > 0
    bridge.skipDemo(); assert bridge.skipped == 1
    bridge.stopDemo(); assert not bridge.running
    bridge.startDemo()
    deadline = time.perf_counter() + 5
    while bridge.running and time.perf_counter() < deadline:
        pump(.02)
    assert bridge.processed == 1000 and not bridge.running
    bridge._done = bridge._completed = bridge._skipped = 0
    bridge._stage = 'configure'; bridge._status = 'UI prototype — ready for a simulated collection.'
    bridge.stateChanged.emit()
    paint_after(lambda: None)
    backend = window.rendererInterface().graphicsApi().name
    result = {'toolkit': 'Qt Quick', 'graphics_api': backend,
              'qt_version': qVersion(), 'pyside_version': pyside_version,
              'subject_count': bridge.source.rowCount(), 'checks': 'passed',
              'first_frame_ms': first_frame_ms,
              'device_pixel_ratio': window.devicePixelRatio(),
              'screen': window.screen().name()}
    if not benchmark:
        return result
    # Same operations as the Tk harness. Exclude fixed settling periods from
    # recorded latency, but wait for an actual Qt frame before stopping timing.
    pump(.5)
    transitions = []
    for label, action in (
        ('maximize', window.showMaximized), ('restore', window.showNormal),
        ('minimize', window.showMinimized), ('restore', window.showNormal),
        ('maximize', window.showMaximized), ('restore', window.showNormal),
    ):
        if label == 'minimize':
            cpu = time.process_time(); wall = time.perf_counter(); action(); app.processEvents()
            sample = {'wall_ms': round((time.perf_counter() - wall)*1000, 2),
                      'cpu_ms': round((time.process_time() - cpu)*1000, 2)}
        else:
            sample = paint_after(action)
        transitions.append({'operation': label, **sample})
        pump(.25)
    resizes = []
    for i in range(12):
        resizes.append(paint_after(lambda i=i: window.resize(1100+i*12, 790+i*6)))
        pump(.025)
    searches = []
    for query in ('p', 'ph', 'phy', 'physics', '', '20', '', 'c', 'co', 'com', ''):
        searches.append(paint_after(lambda query=query: bridge.search(query)))
        pump(.025)
    cpu = time.process_time(); wall = time.perf_counter(); pump(2)
    result.update(transitions=transitions,
                  resize_median_ms=round(statistics.median(x['wall_ms'] for x in resizes), 2),
                  search_median_ms=round(statistics.median(x['wall_ms'] for x in searches), 2),
                  idle_cpu_ms=round((time.process_time()-cpu)*1000, 2),
                  idle_wall_ms=round((time.perf_counter()-wall)*1000, 2),
                  resizes=resizes, searches=searches)
    return result
