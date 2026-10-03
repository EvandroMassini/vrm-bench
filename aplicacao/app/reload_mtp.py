"""MTP reload and read. Does not commit a slot."""
import re
from datetime import datetime, timezone
from .bus_health import check
from .config_dump import ADDRESSES, capture, mask_of
from .param_byte import load_baseline
from .parameters import save_backup
from .registers import map_interface
from .verify_user import crc_flags
from .telemetry import cml_code

from .controller_store import current

def _reload():
    data = current().get('reload')
    if not data:
        raise ValueError('O JSON selecionado não descreve a recarga.')
    return data

class _LiveHex:
    def __init__(self, key):
        self.key = key
    def _value(self):
        return int(_reload()[self.key])
    def __eq__(self, other):
        return self._value() == other
    def __int__(self):
        return self._value()
    def __index__(self):
        return self._value()
    def __format__(self, spec):
        return format(self._value(), spec)

COMANCHE_CLOCK = _LiveHex('clock_register')
BAXTER_CLOCK = _LiveHex('other_clock_register')
OTP_COMMAND = _LiveHex('otp_command')

def decode(line):
    match = re.fullmatch(
        r'OK RELOAD ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) '
        r'([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) '
        r'([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2})',
        line)
    if not match:
        raise ValueError('Resposta RELOAD inválida; estado desconhecido')
    shut, clock_ok, clock_seen, cmd_ok, d0, a5, sample10, sample26, clock_restore, clock_final_ok, clock_final, en_ok, fa, fb = [
        int(item, 16) for item in match.groups()]
    restored = bool(clock_final == 0x20 and en_ok and fa == 0x88 and fb == 0x88)
    return dict(shutdown_confirmed=bool(shut), clock_write_confirmed=bool(clock_ok),
                clock_seen_hex=f'{clock_seen:02X}', command_write_confirmed=bool(cmd_ok),
                command_after_hex=f'{d0:02X}', crc=crc_flags(a5),
                sample10_hex=f'{sample10:02X}', sample26_hex=f'{sample26:02X}',
                clock_restore_attempted=bool(clock_restore), clock_final_read_ok=bool(clock_final_ok),
                clock_final_hex=f'{clock_final:02X}', enable_restored=bool(en_ok),
                enable88_hex=f'{fa:02X}', enable89_hex=f'{fb:02X}', restored=restored,
                reload_confirmed=bool(shut and clock_ok and cmd_ok and restored))

def masked_differences(live_hex, baseline, addresses=None):
    from .config_dump import addresses as selected_addresses
    chosen = tuple(addresses) if addresses is not None else selected_addresses()
    missing = [f'{address:02X}' for address in chosen if f'{address:02X}' not in live_hex or address not in baseline]
    if missing:
        shown = ', '.join(missing[:12])
        if len(missing) > 12:
            shown += f' e mais {len(missing) - 12}'
        raise ValueError('A leitura não cobre o mapa do CI selecionado: ' + shown + '.')
    rows = []
    for address in chosen:
        live = int(live_hex[f'{address:02X}'], 16)
        mask = mask_of(address)
        expected = baseline[address]
        if (live ^ expected) & mask:
            rows.append(dict(register_hex=f'{address:02X}', file_hex=f'{expected:02X}',
                             live_hex=f'{live:02X}', mask_hex=f'{mask:02X}'))
    return rows

def reload_and_read(link,directory,read_map=None):
    from .generic_operations import reload_image
    return reload_image(link,directory,read_map)
