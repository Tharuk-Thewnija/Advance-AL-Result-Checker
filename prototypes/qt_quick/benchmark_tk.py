"""Compare the saved Tk baseline with the Qt protocol. No student files used."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
snapshot = HERE / 'baseline_snapshot'
sys.path.insert(0, str(snapshot if snapshot.exists() else HERE.parents[1]))
from al_results.ui import ScraperApp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as data_dir:
        old_data = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = data_dir
        start = time.perf_counter()
        app = ScraperApp()

        def pump(seconds):
            end = time.perf_counter() + seconds
            while time.perf_counter() < end:
                app.update(); time.sleep(.001)

        def measure(action):
            cpu = time.process_time(); wall = time.perf_counter()
            action(); app.update()
            return {'wall_ms': round((time.perf_counter()-wall)*1000, 2),
                    'cpu_ms': round((time.process_time()-cpu)*1000, 2)}

        try:
            app.update()
            first_frame_ms = round((time.perf_counter()-start)*1000, 2)
            pump(.5)
            transitions = []
            for label, action in (
                ('maximize', lambda: app.state('zoomed')),
                ('restore', lambda: app.state('normal')),
                ('minimize', app.iconify),
                ('restore', lambda: (app.deiconify(), app.state('normal'))),
                ('maximize', lambda: app.state('zoomed')),
                ('restore', lambda: app.state('normal')),
            ):
                transitions.append({'operation': label, **measure(action)})
                pump(.25)
            resizes = []
            for i in range(12):
                resizes.append(measure(lambda i=i: app.geometry(f'{1100+i*12}x{790+i*6}')))
                pump(.025)
            searches = []
            for query in ('p', 'ph', 'phy', 'physics', '', '20', '', 'c', 'co', 'com', ''):
                searches.append(measure(lambda query=query: app.search_var.set(query)))
                pump(.025)
            cpu = time.process_time(); wall = time.perf_counter(); pump(2)
            result = {'toolkit': 'CustomTkinter', 'baseline': str(snapshot),
                      'tk_version': app.tk.call('package', 'require', 'Tk'),
                      'checks': 'completed', 'subject_count': len(app.subject_vars),
                      'first_frame_ms': first_frame_ms,
                      'transitions': transitions, 'resizes': resizes, 'searches': searches,
                      'resize_median_ms': round(statistics.median(x['wall_ms'] for x in resizes), 2),
                      'search_median_ms': round(statistics.median(x['wall_ms'] for x in searches), 2),
                      'idle_cpu_ms': round((time.process_time()-cpu)*1000, 2),
                      'idle_wall_ms': round((time.perf_counter()-wall)*1000, 2)}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
            print(json.dumps(result, indent=2))
        finally:
            app.destroy()
            if old_data is None:
                os.environ.pop('LOCALAPPDATA', None)
            else:
                os.environ['LOCALAPPDATA'] = old_data


if __name__ == '__main__':
    main()
