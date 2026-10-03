"""Official Comanche USER verification mask. Read-only; no OTP reload or program."""
import json
from datetime import datetime, timezone
from pathlib import Path
from .bus_health import check
from .parameters import save_backup

from .controller_store import current
_verify = current()['verify']
USER_START, USER_END = _verify['user_start'], _verify['user_end']
MFR_START, MFR_END = _verify['mfr_start'], _verify['mfr_end']
MASKS = {int(key): value for key, value in _verify['masks'].items()}
IMAGE_PATH = Path(__file__).resolve().parents[1] / 'samples' / 'user_consolidado.json'

def mask_of(address):
    if not 0 <= address <= 255:
        raise ValueError('Endereço fora da tabela')
    return MASKS.get(address, 0xFF)

def crc_flags(value):
    if not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError('A5 inválido')
    bits = ((value >> 2) & 1, (value >> 1) & 1, value & 1)
    return dict(raw_hex=f'{value:02X}', bit2=bits[0], bit1=bits[1], bit0=bits[2],
                active_error=any(bits),
                note='Bits 2, 1 e 0 de A5, na ordem usada por CheckComancheCRC. Sem recarga OTP isto não verifica a MTP.')

def load_image(path=None):
    data = json.loads(Path(path or IMAGE_PATH).read_text(encoding='utf-8-sig'))
    values = data['values_hex']
    image = {address: int(values[f'{address:02X}'], 16) for address in range(USER_START, USER_END + 1)}
    return dict(sha256=data['sha256'], values=image, source=str(path or IMAGE_PATH))

def differences(image, live):
    rows = []
    for address in range(USER_START, USER_END + 1):
        mask = mask_of(address)
        expected, actual = image[address], live[address]
        if (expected & mask) != (actual & mask):
            rows.append(dict(register_hex=f'{address:02X}', image_hex=f'{expected:02X}',
                             live_hex=f'{actual:02X}', mask_hex=f'{mask:02X}'))
    return rows

def compare_live(link, directory, image_path=None):
    image = load_image(image_path)
    result = dict(kind='user_mask_compare', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  complete=False, error=None, programming_enabled=False, reload_sent=False,
                  image_sha256=image['sha256'], user_start_hex='10', user_end_hex='67',
                  ignored_registers=['4F', '50'], mfr_mask_not_applied=['70'],
                  scope='Compara o USER ativo com a imagem PcYes usando a máscara de VerifyComanche. Não recarrega OTP e não programa MTP.')
    try:
        check(link, result)
        live = {}
        for address in range(USER_START, USER_END + 1):
            value = link.register_read(0x70, address)
            if not value['pec_verified']:
                raise ValueError(f'PEC inválido em {address:02X}')
            live[address] = value['value']
        a5 = link.register_read(0x70, 0xA5)
        if not a5['pec_verified']:
            raise ValueError('PEC inválido em A5')
        result['crc'] = crc_flags(a5['value'])
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
