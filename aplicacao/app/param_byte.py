"""Write one active byte and restore it to the session reading. No MTP."""
import re
from datetime import datetime, timezone
from pathlib import Path
from .bus_health import check
from .config_dump import mask_of
from .core import parse_config
from .parameters import save_backup
from .registers import map_interface

from .controller_store import current
from .telemetry import cml_code

class _LiveBlocked:
    def _data(self):
        return frozenset(current()['parameters'].get('blocked') or [])
    def __iter__(self):
        return iter(self._data())
    def __contains__(self, item):
        return item in self._data()
    def __len__(self):
        return len(self._data())

BLOCKED = _LiveBlocked()

def baseline_path():
    name = current()['dump'].get('baseline_file')
    if not name:
        raise ValueError('O JSON selecionado não traz arquivo de referência.')
    return Path(__file__).resolve().parents[1] / 'samples' / name

def load_baseline(path=None):
    entries = parse_config(Path(path or baseline_path()).read_text(encoding='utf-8-sig'))
    return {entry.address: entry.value for entry in entries}

def writable(values):
    params = current()['parameters']
    blocked = frozenset(params.get('blocked') or [])
    masks = params.get('write_masks') or {}
    allowed = []
    for address in sorted(values):
        mask = int(masks.get(str(address), 0) or 0)
        if mask and address not in blocked and params['writable_start'] <= address <= params['writable_end']:
            allowed.append((address, values[address]))
    return allowed

def command(address, expected, target):
    raise ValueError('A escrita usa a transação do protocolo 16. Este atalho antigo não é enviado.')

def change_byte(link,directory,address,target,baseline,mask=None):
    from .generic_operations import change_byte as generic
    return generic(link,directory,address,target,baseline,mask)
