"""Keyboard backlight control through the system's UPower service."""
import re

from hardware import command

SERVICE = 'org.freedesktop.UPower'
PATH = '/org/freedesktop/UPower/KbdBacklight'
INTERFACE = SERVICE + '.KbdBacklight'


def call(method, *arguments):
    output, error = command('busctl', '--system', '--timeout=3s', 'call',
                            SERVICE, PATH, INTERFACE, method, *arguments, timeout=4)
    if error:
        raise RuntimeError('Klavye aydınlatma servisine ulaşılamadı: ' + error)
    return output or ''


def reading(method):
    match = re.fullmatch(r'i (-?\d+)', call(method).strip())
    if not match:
        raise RuntimeError('Klavye aydınlatma servisi geçersiz bir değer döndürdü.')
    return int(match[1])


def status():
    try:
        maximum = reading('GetMaxBrightness')
        if maximum <= 0:
            raise RuntimeError('Bu cihazda ayarlanabilir klavye aydınlatması bulunamadı.')
        brightness = reading('GetBrightness')
        if not 0 <= brightness <= maximum:
            raise RuntimeError('Klavye aydınlatma seviyesi okunamadı.')
        return dict(available=True, brightness=brightness, maximum=maximum, error=None)
    except RuntimeError as error:
        return dict(available=False, brightness=None, maximum=None, error=str(error))


def set_brightness(value):
    if type(value) is not int:
        raise ValueError('Klavye aydınlatma seviyesi tam sayı olmalı.')
    before = status()
    if not before['available']:
        raise RuntimeError(before['error'])
    if not 0 <= value <= before['maximum']:
        raise ValueError('Klavye aydınlatma seviyesi desteklenen aralığın dışında.')
    call('SetBrightness', 'i', str(value))
    after = status()
    if not after['available']:
        raise RuntimeError(after['error'])
    if after['brightness'] != value:
        raise RuntimeError('İstenen klavye aydınlatma seviyesi uygulanmış olarak doğrulanamadı.')
    return after
