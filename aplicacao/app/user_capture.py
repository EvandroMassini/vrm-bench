"""Full USER active-register capture, not OTP reload or programming."""
import hashlib
from datetime import datetime, timezone
from .parameters import save_backup
from .registers import map_interface
from .bus_health import check
from .controller_store import current
from .telemetry import cml_code
from .software_enable import describe, decode_user_pins

class _LiveStatus:
    def _data(self):
        data = current().get('status')
        if not data or not data.get('registers'):
            raise ValueError('O JSON selecionado não descreve os registradores de estado.')
        return tuple(int(item) for item in data['registers'])
    def __iter__(self):
        return iter(self._data())
    def __len__(self):
        return len(self._data())

STATUS = _LiveStatus()

def _bus():
    bus = current()['bus']
    return int(bus['pmbus'], 16), int(bus['direct'], 16), int(bus['speed_khz'])

def _span():
    data = current()['verify']
    return int(data['user_start']), int(data['user_end'])

def decode_status(values):
    data = current().get('status')
    if not data:
        raise ValueError('O JSON selecionado não descreve os registradores de estado.')
    get = lambda register: values[f'{int(register):02X}']['value']
    enable = [int(item) for item in data['enable_registers']]
    loop1, loop2 = describe(get(enable[0])), describe(get(enable[1]))
    chip = int(data['chip_enable_register'])
    startup = int(data['startup_register'])
    crc = int(data['crc_register'])
    return dict(loop1_config_enable_code=loop1['code'], loop2_config_enable_code=loop2['code'],
        loop1_config_enable_name=loop1['name'], loop2_config_enable_name=loop2['name'],
        loop1_chip_enable_bit=(get(chip) >> int(data['loop1_chip_enable_shift'])) & 1,
        loop2_chip_enable_bit=(get(chip) >> int(data['loop2_chip_enable_shift'])) & 1,
        loop1_startup_state_code=get(startup) >> 4, loop2_startup_state_code=get(startup) & 15,
        crc_error_bits_a5=get(crc) & int(data.get('crc_mask', 7)),
        interpretation='Os códigos de enable, CHIP_ENABLE e CRC vêm do JSON deste CI. O nome não é comando e não comprova tensão.')

def collect(link, directory):
    pmbus, direct, speed = _bus()
    start, end = _span()
    status = list(STATUS)
    cml = cml_code()
    r = dict(kind='user_preparation_capture', timestamp_utc=datetime.now(timezone.utc).isoformat(),
        complete=False, error=None, passes=[{}, {}], status_before={}, status_after={}, programming_enabled=False,
        scope=f'USER {start:02X}–{end:02X} do CI selecionado: registradores ativos, duas passagens. Não é leitura direta da MTP nem imagem aprovada para gravação.')
    def read(reg):
        v = link.register_read(pmbus, reg)
        if not v['pec_verified']:
            raise ValueError(f'PEC inválido em {reg:02X}')
        return v
    try:
        check(link, r)
        r['mapping'] = map_interface(link, pmbus, speed)
        if r['mapping']['direct_i2c_address_7bit'] != direct:
            raise ValueError(f'Endereço direto não é {direct:02X}.')
        r['cml_before'] = link.telemetry_read(pmbus, cml)
        for reg in status:
            r['status_before'][f'{reg:02X}'] = read(reg)
        for p in r['passes']:
            for reg in range(start, end + 1):
                p[f'{reg:02X}'] = read(reg)
        for reg in status:
            r['status_after'][f'{reg:02X}'] = read(reg)
        r['cml_after'] = link.telemetry_read(pmbus, cml)
        r['changed_registers'] = [key for key in r['passes'][0] if r['passes'][0][key]['value'] != r['passes'][1][key]['value']]
        r['status_decoded_before'] = decode_status(r['status_before'])
        r['status_decoded_after'] = decode_status(r['status_after'])
        r['status_changed_registers'] = [key for key in r['status_before'] if r['status_before'][key]['value'] != r['status_after'][key]['value']]
        r['complete'] = True
        r['stable_user'] = not r['changed_registers']
        r['values'] = r['passes'][1]
        r['sha256_user_pass2'] = hashlib.sha256(bytes(r['values'][f'{reg:02X}']['value'] for reg in range(start, end + 1))).hexdigest()
        r['user_pin_fields'] = decode_user_pins(r['values'])
        r['warnings'] = []
        if not r['stable_user']:
            r['warnings'].append('USER mudou entre passagens; não consolidar como imagem estável.')
        if r['cml_before']['value_raw'] or r['cml_after']['value_raw']:
            r['warnings'].append('STATUS_CML não zerado.')
    except Exception as exc:
        r['error'] = str(exc)
    r['report_path'] = save_backup(r, directory)
    return r
