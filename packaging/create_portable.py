"""Create a portable archive without requiring exclusive access to input files."""
import argparse
from pathlib import Path
import time
import zipfile


def create(folder,output):
    folder=Path(folder).resolve(); output=Path(output).resolve()
    if not folder.is_dir() or output.is_relative_to(folder):
        raise ValueError('Choose an application folder and a ZIP outside that folder.')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_name(output.name+'.partial')
    count=0
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in sorted(folder.rglob('*')):
                if not path.is_file(): continue
                for attempt in range(3):
                    try:
                        archive.write(path,(Path(folder.name)/path.relative_to(folder)).as_posix())
                        break
                    except PermissionError:
                        if attempt==2: raise
                        time.sleep(.5*(attempt+1))
                count+=1
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None: raise RuntimeError('Portable archive failed its CRC check.')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Portable ZIP verified: {count} files, {output.stat().st_size} bytes, {output}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); create(args.folder,args.output)
