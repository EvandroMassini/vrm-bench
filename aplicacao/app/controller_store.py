"""Controller descriptions live in controllers/*.json, one file per device."""
import json
import sys
from pathlib import Path

_chips = {}
_current = None

def directory():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'controllers'
    return Path(__file__).resolve().parents[1] / 'controllers'

def load(folder=None):
    global _current
    folder = Path(folder) if folder else directory()
    found = {}
    if folder.is_dir():
        for path in sorted(folder.glob('*.json')):
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict) or not data.get('id'):
                continue
            data['path'] = str(path)
            found[data['id']] = data
    _chips.clear()
    _chips.update(found)
    if _current not in _chips:
        _current = 'IR3567B' if 'IR3567B' in _chips else (next(iter(_chips), None))
    return dict(_chips)

def names():
    if not _chips:
        load()
    return list(_chips)

def get(name):
    if not _chips:
        load()
    return _chips[name]

def current():
    if not _chips:
        load()
    if _current is None:
        raise ValueError('Nenhum controlador em controllers.')
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

load()
