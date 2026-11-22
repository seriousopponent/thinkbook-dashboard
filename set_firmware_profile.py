#!/usr/bin/python3
"""Set one profile explicitly advertised by the standard Linux ACPI interface."""
from pathlib import Path
import sys

BASE = Path('/sys/firmware/acpi')
SUPPORTED = {'low-power', 'balanced', 'performance', 'quiet', 'cool', 'balanced-performance'}


def set_profile(profile):
    choices = (BASE / 'platform_profile_choices').read_text().split()
    if profile not in SUPPORTED or profile not in choices:
        raise ValueError('The firmware does not advertise this profile.')
    (BASE / 'platform_profile').write_text(profile + '\n')
    actual = (BASE / 'platform_profile').read_text().strip()
    if actual != profile:
        raise RuntimeError(f'Firmware reports {actual} after requesting {profile}.')
    return actual


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Exactly one profile argument is required.')
        print(set_profile(sys.argv[1]))
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
