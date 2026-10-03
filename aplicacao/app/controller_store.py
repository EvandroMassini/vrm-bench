"""Controller descriptions live in controllers/*.json, one file per device."""
import json
import sys
from pathlib import Path

_chips = {}
_current = None
_errors = {}

def directory():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'controllers'
    return Path(__file__).resolve().parents[1] / 'controllers'

def load(folder=None):
    global _current
    folder = Path(folder) if folder else directory()
    found = {}
    _errors.clear()
    if folder.is_dir():
        for path in sorted(folder.glob('*.json')):
            try:
                from .profile_schema import validate
                data = validate(json.loads(path.read_text(encoding='utf-8-sig')))
                if data['id'] in found: raise ValueError('id duplicado: '+data['id'])
                data['path'] = str(path)
                found[data['id']] = data
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                _errors[str(path)] = str(exc)
    _chips.clear()
    _chips.update(found)
    if _current not in _chips:
        _current = None
    return dict(_chips)

def names():
    if not _chips:
        load()
    return list(_chips)

def get(name):
    if not _chips:
        load()
    return _chips[name]

def selected():
    if not _chips:
        load()
    return _current if _current in _chips else None

def clear():
    global _current
    _current = None

def current():
    if not _chips:
        load()
    if _current is None or _current not in _chips:
        raise ValueError('Selecione o CI correto na lista Controlador antes de ler a placa.')
    return _chips[_current]

def select(name):
    global _current
    if not _chips:
        load()
    if name not in _chips:
        raise KeyError(name)
    _current = name
    return _chips[name]

def default():
    return current()

def field(symbol, name=None):
    chip = get(name) if name else current()
    for item in chip['fields']:
        if item['symbol'] == symbol:
            return item
    raise KeyError(symbol)

def region_name(profile, address):
    if not _chips:
        load()
    chip = _chips.get(profile)
    if chip is None:
        return None
    for item in chip['regions']:
        if item['start'] <= address <= item['end']:
            return item['name']
    return chip['region_else']

def model_hex(name=None):
    chip = get(name) if name else current()
    return chip['identity']['model_hex']

def identity_register_text(chip=None):
    chip = chip or current()
    register = ((chip.get('protocol') or {}).get('identity') or {}).get('register')
    if isinstance(register, int):
        return f'{register:02X}'
    return (chip.get('bus') or {}).get('register') or ''

load()


def errors():
    return dict(_errors)
