"""Parameter file in the three-column dump format. Read-only."""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from .bus_health import check
from .core import compare, parse_config
from .parameters import save_backup
from .registers import map_interface

from .controller_store import current
from .telemetry import cml_code

def _dump():
    return current()['dump']

def addresses():
    return tuple(int(item) for item in _dump()['addresses'])

class _LiveAddresses:
    def __iter__(self):
        return iter(addresses())
    def __len__(self):
        return len(addresses())
    def __getitem__(self, item):
        return addresses()[item]
    def __contains__(self, item):
        return item in addresses()

class _LiveMap(dict):
    def __init__(self, loader):
        super().__init__()
        self._loader = loader
    def _data(self):
        return self._loader()
    def __iter__(self):
        return iter(self._data())
    def __len__(self):
        return len(self._data())
    def __contains__(self, key):
        return key in self._data()
    def __getitem__(self, key):
        return self._data()[key]
    def get(self, key, default=None):
        return self._data().get(key, default)
    def keys(self):
        return self._data().keys()
    def items(self):
        return self._data().items()

def _mask_overrides():
    return {int(key): value for key, value in (_dump().get('mask_overrides') or {}).items()}

def _trim_masks():
    dump = _dump()
    end = int(dump.get('trim_end') or 0)
    special = dump.get('trim_special') or {}
    fallback = int(dump.get('trim_mask') or 0)
    return {address: int(special.get(str(address), fallback)) for address in range(end + 1)}

def _blocked_write():
    return frozenset(_dump().get('blocked_write') or [])

ADDRESSES = _LiveAddresses()
MASK_OVERRIDES = _LiveMap(_mask_overrides)
TRIM_MASKS = _LiveMap(_trim_masks)
BLOCKED_WRITE = _LiveMap(lambda: {item: True for item in _blocked_write()})

def baseline_sha256():
    return _dump().get('baseline_sha256')

def mask_of(address):
    if not isinstance(address, int) or not 0 <= address <= 255:
        raise ValueError('Endereço fora do mapa')
    dump = _dump()
    overrides = {int(key): value for key, value in dump['mask_overrides'].items()}
    if address in overrides:
        return overrides[address]
    if address <= dump['trim_boundary']:
        if address > dump['trim_end']:
            return int(dump['trim_mask'])
        special = dump.get('trim_special') or {}
        return int(special.get(str(address), dump['trim_mask']))
    return dump['default_mask']

def _codes(items):
    shown = ', '.join(f'{address:02X}' for address in items[:12])
    if len(items) > 12:
        shown += f' e mais {len(items) - 12}'
    return shown

def mismatch_message(values):
    """None when the bytes just read are exactly the selected controller map."""
    chip = current()
    expected = set(addresses())
    got = set(values)
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    if not missing and not extra:
        return None
    lines = [f'A leitura não corresponde ao CI selecionado ({chip["id"]}). O processo foi interrompido.']
    if missing:
        lines.append('Parâmetros do JSON não encontrados na placa: ' + _codes(missing) + '.')
    if extra:
        lines.append('Registradores devolvidos que não estão no JSON selecionado: ' + _codes(extra) + '.')
    lines.append('Selecione o CI correto antes de ler de novo.')
    return '\n'.join(lines)

def format_text(values):
    lines = []
    for address in addresses():
        value = values[address]
        if not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError(f'Valor inválido em {address:02X}')
        lines.append(f'{address:02X} {value:02X} {mask_of(address):02X}')
    return '\r\n'.join(lines) + '\r\n'

def save_text(text, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (current()['id'] + '_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '.txt')
    with path.open('x', encoding='ascii', newline='') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return str(path)

def difference_plan(live, entries):
    rows = []
    enable = set(int(item) for item in (current().get('status') or {}).get('enable_registers') or [])
    blocked = frozenset(_dump().get('blocked_write') or [])
    for entry in entries:
        actual = live.get(entry.address)
        canonical = mask_of(entry.address)
        rows.append(dict(
            register_hex=f'{entry.address:02X}',
            live_hex=None if actual is None else f'{actual:02X}',
            file_hex=f'{entry.value:02X}',
            file_mask_hex=f'{entry.mask:02X}',
            canonical_mask_hex=f'{canonical:02X}',
            mask_matches_map=canonical == entry.mask,
            comparison=compare(entry, actual),
            enable_register=entry.address in enable,
            blocked_for_future_write=entry.address in blocked))
    diverged = [row for row in rows if row['comparison'] == 'Diverge']
    return dict(kind='masked_dump_diff', programming_enabled=False, write_attempted=False,
                diverge_count=len(diverged),
                actionable_later=[row for row in diverged if not row['blocked_for_future_write']],
                blocked_differences=[row for row in diverged if row['blocked_for_future_write']],
                mask_disagreements=[row['register_hex'] for row in rows if not row['mask_matches_map']],
                rows=rows,
                note='Diferenças sob a máscara da terceira coluna. Nenhum byte foi escrito.')

def _bus():
    bus = current()['bus']
    return int(bus['pmbus'], 16), int(bus['direct'], 16), int(bus['speed_khz'])

def _read_pass(link, chosen, progress, done, pmbus):
    values = {}
    for address in chosen:
        reading = link.register_read(pmbus, address)
        if not reading['pec_verified']:
            raise ValueError(f'PEC inválido em {address:02X}')
        values[address] = reading['value']
        done[0] += 1
        if progress and done[0] % 26 == 0:
            progress(done[0], len(chosen) * 2)
    return values

def capture(link, directory, progress=None, address_list=None):
    chosen = tuple(address_list) if address_list is not None else addresses()
    pmbus, _direct, speed = _bus()
    dump = _dump()
    overrides = {int(key): value for key, value in (dump.get('mask_overrides') or {}).items()}
    blocked = frozenset(dump.get('blocked_write') or [])
    result = dict(kind='config_dump', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  complete=False, error=None, programming_enabled=False, write_attempted=False,
                  addresses=[f'{address:02X}' for address in chosen],
                  mask_overrides={f'{address:02X}': f'{mask:02X}' for address, mask in overrides.items()},
                  blocked_write=[f'{address:02X}' for address in sorted(blocked)],
                  scope='Lê o mapa do CI selecionado pelo PMBus e grava endereço, valor ativo e máscara. Não recarrega OTP e não escreve parâmetros.')
    try:
        check(link, result)
        result['mapping'] = map_interface(link, pmbus, speed)
        result['cml_before'] = link.telemetry_read(pmbus, cml_code())
        done = [0]
        first = _read_pass(link, chosen, progress, done, pmbus)
        second = _read_pass(link, chosen, progress, done, pmbus)
        result['cml_after'] = link.telemetry_read(pmbus, cml_code())
        changed = [f'{address:02X}' for address in chosen if first[address] != second[address]]
        result['changed_registers'] = changed
        result['stable'] = not changed
        result['values'] = {f'{address:02X}': f'{second[address]:02X}' for address in chosen}
        span = range(0x10, 0x68)
        if all(address in second for address in span):
            user = bytes(second[address] for address in span)
            result['user_sha256'] = hashlib.sha256(user).hexdigest()
            result['user_matches_pcyes_image'] = result['user_sha256'] == dump['baseline_sha256']
        result['warnings'] = []
        if changed:
            result['warnings'].append('O mapa mudou entre as passagens; o TXT não foi gravado.')
        if result['cml_before']['value_raw'] or result['cml_after']['value_raw']:
            result['warnings'].append('STATUS_CML não zerado.')
        result['complete'] = True
        if result['stable']:
            text = format_text(second)
            result['text_sha256'] = hashlib.sha256(text.encode('ascii')).hexdigest()
            result['txt_path'] = save_text(text, Path(directory) / 'dumps')
        else:
            result['txt_path'] = None
    except Exception as exc:
        result['error'] = str(exc)
    result['report_path'] = save_backup(result, Path(directory) / 'backups')
    return result

def plan_against_file(live_hex, text):
    live = {int(key, 16): int(value, 16) for key, value in live_hex.items()}
    return difference_plan(live, parse_config(text))
