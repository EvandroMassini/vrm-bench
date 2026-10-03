"""USER verification mask. Read-only; no OTP reload or program."""
import json
from datetime import datetime, timezone
from pathlib import Path
from .bus_health import check
from .parameters import save_backup

from .controller_store import current

def _verify():
    return current()['verify']

def _span():
    data = _verify()
    return int(data['user_start']), int(data['user_end'])

def _masks():
    return {int(key): value for key, value in (_verify().get('masks') or {}).items()}

def _image_path():
    name = _verify().get('image_file')
    if not name:
        raise ValueError('O JSON selecionado não traz imagem de verificação.')
    return Path(__file__).resolve().parents[1] / 'samples' / name

def mask_of(address):
    if not 0 <= address <= 255:
        raise ValueError('Endereço fora da tabela')
    return _masks().get(address, 0xFF)

def crc_flags(value, mask=7):
    if not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError('CRC inválido')
    bits = ((value >> 2) & 1, (value >> 1) & 1, value & 1)
    return dict(raw_hex=f'{value:02X}', bit2=bits[0], bit1=bits[1], bit0=bits[2],
                active_error=bool(value & mask),
                note='Bits cobertos pela máscara de CRC do JSON. Sem recarga isto não verifica a memória permanente.')

def load_image(path=None):
    source = Path(path) if path else _image_path()
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    values = data['values_hex']
    start, end = _span()
    image = {address: int(values[f'{address:02X}'], 16) for address in range(start, end + 1)}
    return dict(sha256=data['sha256'], values=image, source=str(source))

def differences(image, live):
    rows = []
    start, end = _span()
    for address in range(start, end + 1):
        mask = mask_of(address)
        expected, actual = image[address], live[address]
        if (expected & mask) != (actual & mask):
            rows.append(dict(register_hex=f'{address:02X}', image_hex=f'{expected:02X}',
                             live_hex=f'{actual:02X}', mask_hex=f'{mask:02X}'))
    return rows

def compare_live(link, directory, image_path=None):
    image = load_image(image_path)
    data = _verify()
    start, end = _span()
    bus = current()['bus']
    pmbus = int(bus['pmbus'], 16)
    crc_register = int(data['crc_register'])
    result = dict(kind='user_mask_compare', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  complete=False, error=None, programming_enabled=False, reload_sent=False,
                  image_sha256=image['sha256'], user_start_hex=f'{start:02X}', user_end_hex=f'{end:02X}',
                  ignored_registers=list(data.get('ignored') or []),
                  mfr_mask_not_applied=list(data.get('mfr_unmasked') or []),
                  scope='Compara o USER ativo com a imagem deste CI usando a máscara do JSON. Não recarrega OTP e não programa MTP.')
    try:
        check(link, result)
        live = {}
        for address in range(start, end + 1):
            value = link.register_read(pmbus, address)
            if not value['pec_verified']:
                raise ValueError(f'PEC inválido em {address:02X}')
            live[address] = value['value']
        a5 = link.register_read(pmbus, crc_register)
        if not a5['pec_verified']:
            raise ValueError(f'PEC inválido em {crc_register:02X}')
        result['crc'] = crc_flags(a5['value'], int(data.get('crc_mask', 7)))
        result['mismatches'] = differences(image['values'], live)
        result['mismatch_count'] = len(result['mismatches'])
        result['user_masked_equal'] = result['mismatch_count'] == 0
        result['complete'] = True
        if not result['user_masked_equal']:
            result['warnings'] = ['Há bytes USER fora da máscara. Isso não autoriza gravação.']
    except Exception as exc:
        result['error'] = str(exc)
    result['report_path'] = save_backup(result, directory)
    return result
