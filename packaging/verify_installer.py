"""Verify an InstallTest build without touching the normal product installation."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def run(setup,output):
    setup=Path(setup).resolve(); output=Path(output).resolve()
    if not setup.name.startswith('ALResultsCollector-InstallTest-'):
        raise ValueError('Use an installer compiled with /DInstallTest, not the normal installer.')
    output.mkdir(parents=True,exist_ok=False)
    target=output/'program'; working=output/'empty-cwd'; working.mkdir()
    assert target.resolve().is_relative_to(output)
    env=dict(os.environ,LOCALAPPDATA=str(output/'appdata'))
    for name in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH'):
        env.pop(name,None)
    windows=Path(os.environ['SystemRoot'])
    env['PATH']=os.pathsep.join(map(str,[windows/'System32',windows]))
    marker=Path(env['LOCALAPPDATA'])/'ALResultsCollectorQt'/'ALResultsCollector'/'preserve-user-data.txt'
    marker.parent.mkdir(parents=True); marker.write_text('Keep user data after uninstall.',encoding='utf-8')
    startupinfo=subprocess.STARTUPINFO()
    startupinfo.dwFlags|=subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow=0
    def execute(args,timeout=180,*,hidden=False):
        return subprocess.run([str(a) for a in args],cwd=working,env=env,check=True,
                              timeout=timeout,startupinfo=startupinfo if hidden else None)
    installed=False
    try:
        execute([setup,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',
                 '/DIR='+str(target),'/LOG='+str(output/'install.log')],hidden=True)
        installed=True
        exe=target/'ALResultsCollector.exe'
        assert exe.is_file()
        startup=output/'startup.json'
        execute([exe,'--smoke-test','--report',startup],45)
        data=json.loads(startup.read_text())
        assert data['loaded'] and data['captcha_mode']=='Manual' and data['max_workers']==5
        automatic=output/'nonecap.json'
        execute([exe,'--verify-nonecap','--report',automatic])
        checked=json.loads(automatic.read_text())
        assert checked['checks']=='passed' and checked['completed']==2
    finally:
        uninstall=target/'unins000.exe'
        if uninstall.exists():
            execute([uninstall,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(output/'uninstall.log')],hidden=True)
    assert installed and not (target/'ALResultsCollector.exe').exists()
    assert marker.read_text(encoding='utf-8')=='Keep user data after uninstall.'
    result=dict(checks='passed',version=data['version'],installed_startup='passed',automatic='passed',
                uninstall='passed',user_data_preserved=True,normal_installation_untouched=True)
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); run(args.setup,args.output)
