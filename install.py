#!/usr/bin/python3
"""Install a built dashboard and application-menu launcher for the current user."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil

SOURCE = Path(__file__).resolve().parent
RUNTIME = ('native.py', 'service.py', 'hardware.py', 'keyboard.py', 'dashboard.py', 'osd.py',
           'set_firmware_profile.py', 'icon.svg')


def quoted_exec(path):
    escaped = str(path).replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        escaped = escaped.replace(char, '\\' + char)
    return '"' + escaped.replace('\\', '\\\\') + '"'


def install(data_home):
    target = data_home / 'thinkbook-dashboard'
    if target.resolve() == SOURCE:
        raise SystemExit('Run the installer from a source checkout, not the installed directory.')
    if not (SOURCE / 'ui/dist/index.html').is_file():
        raise SystemExit('Build the interface first: npm ci --prefix ui && npm run build --prefix ui')
    if target.exists():
        backup = data_home / ('thinkbook-dashboard-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        shutil.copytree(target, backup, symlinks=True)
        print(f'Previous installation backed up to {backup}')
    target.mkdir(parents=True, exist_ok=True)
    for filename in RUNTIME:
        shutil.copy2(SOURCE / filename, target / filename)
    shutil.copytree(SOURCE / 'ui/dist', target / 'ui/dist', dirs_exist_ok=True)
    applications = data_home / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    entry = applications / 'io.github.thinkbook.Dashboard.desktop'
    icon = str(target / 'icon.svg').replace('\\', '\\\\')
    entry.write_text(f'''[Desktop Entry]
Type=Application
Name=ThinkBook Dashboard
Comment=Power, graphics and system controls for ThinkBook on Linux
Exec=/usr/bin/python3 {quoted_exec(target / 'native.py')}
Icon={icon}
Terminal=false
Categories=Settings;System;
StartupNotify=true
Actions=Legacy;

[Desktop Action Legacy]
Name=Klasik arayüzü aç
Exec=/usr/bin/python3 {quoted_exec(target / 'dashboard.py')}
''')
    entry.chmod(0o755)
    print(f'Installed to {target}')
    print(f'Application launcher: {entry}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-home', type=Path,
                        default=Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')),
                        help='Application data directory (default: XDG_DATA_HOME or ~/.local/share)')
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error('Run this installer as your desktop user, without sudo.')
    install(args.data_home.expanduser().resolve())
