import os
from pathlib import Path
import subprocess
from ctf_unlock.engine import find_7zip

ENGINE = os.environ.get('CTF_UNLOCK_7ZIP') or find_7zip()


def archive(root: Path, kind='zip', password='CTF42', name=None, headers=False, aes=False):
    folder = root / 'fichiers avec espaces'
    folder.mkdir(exist_ok=True)
    payload = folder / 'preuve été.txt'
    payload.write_text('CTF Unlock : preuve intégrale\n' * 8, encoding='utf-8')
    target = root / (name or f'challenge {kind}.data')
    args = [ENGINE, 'a', f'-t{kind}', '-y', '-mmt=1']
    if password:
        args.append('-p' + password)
    if headers:
        args.append('-mhe=on')
    if aes:
        args.append('-mem=AES256')
    result = subprocess.run([*args, '--', str(target), str(payload)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stdout.decode(errors='replace'))
    return target
