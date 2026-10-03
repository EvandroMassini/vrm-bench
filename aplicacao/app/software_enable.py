"""Software chip-enable legend and one reversible soft-shutdown experiment."""
import re
from datetime import datetime, timezone
from .bus_health import check, explanation
from .registers import map_interface
from .controller_store import current
from .telemetry import cml_code

def _status():
    data = current().get('status')
    if not data:
        raise ValueError('O JSON selecionado não descreve os registradores de estado.')
    return data

def _bus():
    bus = current()['bus']
    return int(bus['pmbus'], 16), int(bus['direct'], 16), int(bus['speed_khz'])

def describe(value):
    if not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError('Byte inválido')
    data = _status()
    shift = int(data.get('enable_code_shift', 6))
    names = {index: name for index, name in enumerate(data.get('enable_codes') or [])}
    code = (value >> shift) & 3
    return dict(raw_hex=f'{value:02X}', code=code, name=names.get(code, 'Reservado'),
                preserved_low_bits_hex=f'{value & ((1 << shift) - 1):02X}')

def pin_bit(value, offset):
    return (value >> (7 - offset)) & 1

def decode_user_pins(values):
    pins = _status().get('pin_bits') or []
    if not pins:
        raise ValueError('O JSON selecionado não descreve os bits de pino de enable.')
    def byte(reg):
        return values[f'{int(reg):02X}']['value']
    found = {item['name']: pin_bit(byte(item['register']), int(item['offset'])) for item in pins}
    found['source'] = 'USER ativo. Offset contado a partir do MSB. Não é comando.'
    return found

def decode(response):
    pattern = r'OK ENSOFT' + r' ([0-9A-F]{2})' * 17
    m = re.fullmatch(pattern, response)
    if not m:
        raise ValueError('Resposta ENSOFT inválida; restauração não confirmada.')
    nums = [int(x, 16) for x in m.groups()]
    if any(x not in (0, 1) for x in (nums[0], nums[1], nums[2], nums[4], nums[6], nums[8], nums[10], nums[11], nums[12], nums[14])):
        raise ValueError('Flags ENSOFT inválidos; restauração não confirmada.')
    w1, w2, r1, c88, r2, c89, r96, p96, ra9, pa9, s1, s2, f1, o88, f2, o89, mode = nums
    data = _status()
    baseline = int(data['baseline_value'])
    soft = int(data['soft_value'])
    changed = bool(w1 and w2 and r1 and r2 and c88 == soft and c89 == soft)
    restored = bool(s1 and s2 and f1 and f2 and o88 == baseline and o89 == baseline)
    return dict(
        write88_ack=bool(w1), write89_ack=bool(w2),
        read88_ok=bool(r1), changed88_hex=f'{c88:02X}',
        read89_ok=bool(r2), changed89_hex=f'{c89:02X}',
        status96_read_ok=bool(r96), status96_hex=f'{p96:02X}',
        statusA9_read_ok=bool(ra9), statusA9_hex=f'{pa9:02X}',
        restore88_ack=bool(s1), restore89_ack=bool(s2),
        final88_read_ok=bool(f1), final88_hex=f'{o88:02X}',
        final89_read_ok=bool(f2), final89_hex=f'{o89:02X}',
        mode_hex=f'{mode:02X}',
        change_confirmed=changed, restoration_confirmed=restored)

def _reg(link, pmbus, reg):
    value = link.register_read(pmbus, reg)
    if not value['pec_verified'] or value['value'] not in range(256):
        raise ValueError(f'PEC inválido em {reg:02X}; nenhuma escrita realizada.')
    return value

def experiment(link,before_send=None,hold=False):
    from .generic_operations import enable
    return enable(link,before_send,hold)

def describe_status96(raw_hex):
    value = int(raw_hex, 16)
    data = _status()
    return dict(raw_hex=raw_hex,
                loop1_chip_enable_bit=(value >> int(data['loop1_chip_enable_shift'])) & 1,
                loop2_chip_enable_bit=(value >> int(data['loop2_chip_enable_shift'])) & 1,
                note='Estado lido, não comando. Enable em 1 não comprova regulação; 0 não comprova ausência de tensão.')
