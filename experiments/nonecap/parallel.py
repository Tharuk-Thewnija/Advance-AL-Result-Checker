"""Browser workers own their sessions; this coordinator alone owns SQLite."""
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
import time

from selenium.common.exceptions import TimeoutException, WebDriverException

from al_results.excel_io import validate_rows
from al_results.models import RowResult, WorkerEvent
from al_results.parsing import parse_results


def collect_parallel(config, workbook, store, emit, stop, skips, session_factory, core,
                     pause, pause_reason, workers=2, *, pause_kind=None):
    started = time.perf_counter()
    terminal, reason, error = 'finished', '', ''
    counts = dict(total=len(workbook.frame), processed=0, completed=0, skipped=0, failed=0)
    keys = {'Completed':'completed', 'Skipped':'skipped', 'Error':'failed'}
    jobs, outputs = Queue(), Queue()
    row_seconds = []
    saving_failed = False

    def worker(number):
        session = None
        try:
            while not stop.is_set() and not pause.is_set():
                try: position, nic, invalid = jobs.get_nowait()
                except Empty: break
                skips[number-1].clear()
                emit(WorkerEvent('current', {'position':position,'nic':nic}))
                emit(WorkerEvent('log', {'text':f'Worker {number}: opening row {position + 1}.'}))
                row_started = time.perf_counter()
                if invalid:
                    result = RowResult(position,'Skipped',{},invalid)
                else:
                    if session is None: session = session_factory(number)
                    try:
                        text = session.fetch(nic,config,stop,skips[number-1],lambda: emit(WorkerEvent('log',{
                            'text':f'Worker {number}, row {position+1}: MANUAL ACTION REQUIRED — complete CAPTCHA and submit in this Chrome window.'})))
                        values = parse_results(text,config.subject_ids,config.fields)
                        missing = [sid for sid in config.subject_ids if values.get(f'subject:{sid}') is None]
                        result = RowResult(position,'Completed',values,
                                           'Selected subject result not present: '+', '.join(missing) if missing else '')
                    except core.SkipCurrentRow:
                        result = RowResult(position,'Skipped',{},f'Skipped on worker {number}')
                    except core.StopRequested:
                        if not pause.is_set(): stop.set()
                        break
                    except TimeoutException:
                        if stop.is_set(): break
                        result = RowResult(position,'Error',{},'Timed out waiting for submitted results')
                outputs.put(('row',(result,number,time.perf_counter()-row_started)))
        except core.StopRequested:
            if not pause.is_set(): stop.set()
        except Exception as exc:
            stop.set()
            outputs.put(('error',exc))
        finally:
            if session is not None:
                try: session.close()
                except Exception: pass
            outputs.put(('done',number))

    try:
        for result in store.results():
            counts['processed'] += 1; counts[keys[result.status]] += 1
        pending = set(store.pending_positions())
        for row in validate_rows(workbook):
            if row[0] in pending: jobs.put(row)
        actual = min(workers,jobs.qsize())
        with ThreadPoolExecutor(max_workers=max(1,actual),thread_name_prefix='NoneCAP-browser') as pool:
            futures = [pool.submit(worker,number) for number in range(1,actual+1)]
            done = 0
            while done < actual:
                kind, payload = outputs.get()
                if kind == 'done': done += 1
                elif kind == 'error':
                    if terminal != 'fatal':
                        if isinstance(payload,WebDriverException) and core.browser_closed_error(payload):
                            terminal,reason = 'stopped','browser_closed'
                        else:
                            terminal,reason,error = 'fatal','',getattr(payload,'msg',None) or str(payload)
                elif kind == 'row' and not saving_failed:
                    result,number,elapsed = payload
                    try:
                        store.save(result)
                    except Exception as exc:
                        saving_failed = True; stop.set()
                        terminal,reason,error = 'fatal','',str(exc)
                        continue
                    counts['processed'] += 1; counts[keys[result.status]] += 1
                    row_seconds.append(elapsed)
                    emit(WorkerEvent('progress',dict(counts)))
                    emit(WorkerEvent('log',{'text':f'Worker {number}, row {result.position+1}: {result.status} ({elapsed:.1f}s)'}))
            for future in futures: future.result()
        if terminal != 'fatal' and not reason:
            if pause.is_set(): terminal,reason,error = 'stopped',pause_kind() if pause_kind else 'automatic_limit',pause_reason()
            elif stop.is_set(): terminal = 'stopped'
    except Exception as exc:
        stop.set(); terminal,reason,error = 'fatal','',str(exc)
    finally:
        store.close()
    elapsed = time.perf_counter()-started
    metrics = dict(workers=workers,rows=len(row_seconds),elapsed_seconds=elapsed,
                   mean_row_seconds=sum(row_seconds)/len(row_seconds) if row_seconds else 0,
                   rows_per_minute=len(row_seconds)*60/elapsed if elapsed else 0)
    emit(WorkerEvent('log',{'text':f"Batch: {workers} workers, {len(row_seconds)} newly saved rows in {elapsed:.1f}s ({metrics['rows_per_minute']:.1f} rows/min)."}))
    emit(WorkerEvent(terminal,{**counts,'reason':reason,'error':error}))
    return metrics
