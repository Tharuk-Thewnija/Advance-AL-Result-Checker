"""Verify a relocated Windows bundle with private app-data and no source search path."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def verify(executable, output):
    executable = Path(executable).resolve(); output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    relocated = output / 'portable' / executable.parent.name
    shutil.copytree(executable.parent, relocated)
    exe = relocated / executable.name
    working = output / 'empty-working-directory'; working.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(output / 'appdata'))
    for name in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                 'QML_IMPORT_PATH', 'QML2_IMPORT_PATH'):
        env.pop(name, None)
    windows = Path(os.environ['SystemRoot'])
    env['PATH'] = os.pathsep.join(map(str, [windows / 'System32', windows]))
    payload = relocated / '_internal'
    assert (payload / 'qt_app/qml/Main.qml').is_file()
    manager = payload / 'selenium/webdriver/common/windows/selenium-manager.exe'
    assert manager.is_file()
    assert not list(payload.rglob('*tkinter*'))
    assert not list(payload.rglob('icuuc.dll'))
    assert (payload / 'third_party_licenses/LGPL-3.0.txt').is_file()
    assert (payload / 'al_results/collector.py').is_file()
    assert (payload / 'al_results/nonecap/browser_hook.js').is_file()
    subprocess.run([str(manager), '--version'], env=env, cwd=working, check=True, timeout=20)
    startup = output / 'startup.json'
    subprocess.run([str(exe), '--smoke-test', '--report', str(startup)], env=env, cwd=working, check=True, timeout=45)
    data = json.loads(startup.read_text())
    assert data['loaded'] and data['toolkit'] == 'QtQuick' and data['subjects'] == 63
    assert data['captcha_mode']=='Manual' and data['max_workers']==5 and data['automatic_controls']
    browser_report = output / 'browser.json'
    subprocess.run([str(exe), '--verify-browser', '--report', str(browser_report)], env=env, cwd=working, check=True, timeout=120)
    browser = json.loads(browser_report.read_text())
    assert browser['checks'] == 'passed' and browser['closed_session_detected']
    mock_report = output / 'mock.json'
    subprocess.run([str(exe), '--verify-mock', '--report', str(mock_report)], env=env, cwd=working, check=True, timeout=150)
    mock = json.loads(mock_report.read_text())
    assert mock['counts'] == {'total': 1500, 'processed': 1500, 'completed': 1455, 'skipped': 30, 'failed': 15}
    assert mock['checks'].startswith('passed:')
    assert Path(mock['last_export']).is_file()
    automatic_report=output/'nonecap-local.json'
    subprocess.run([str(exe),'--verify-nonecap','--report',str(automatic_report)],env=env,cwd=working,check=True,timeout=180)
    automatic=json.loads(automatic_report.read_text())
    assert automatic['checks']=='passed' and automatic['completed']==2 and automatic['same_job_receipt_rechecks']==1
    summary = dict(version=data['version'], startup='passed', graphics_api=data['graphics_api'],
                   relocated_exe=str(exe), browser='passed', browser_version=browser['browser_version'],
                   mock='passed', counts=mock['counts'],automatic='passed',automatic_details=automatic)
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New, empty verification directory')
    args = parser.parse_args()
    verify(args.exe, args.output)
