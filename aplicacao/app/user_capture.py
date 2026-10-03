"""Full USER active-register capture, not OTP reload or programming."""
import hashlib
from datetime import datetime,timezone
from .parameters import save_backup
from .registers import map_interface
from .bus_health import check
from .software_enable import describe, decode_user_pins
STATUS=(0x88,0x89,0x96,0xA5,0xA6,0xA7,0xA9)

def decode_status(values):
    get=lambda k:values[f'{k:02X}']['value']
    loop1, loop2 = describe(get(0x88)), describe(get(0x89))
    return dict(loop1_config_enable_code=loop1['code'],loop2_config_enable_code=loop2['code'],
        loop1_config_enable_name=loop1['name'],loop2_config_enable_name=loop2['name'],
        loop1_chip_enable_bit=(get(0x96)>>5)&1,loop2_chip_enable_bit=(get(0x96)>>4)&1,
        loop1_startup_state_code=get(0xA9)>>4,loop2_startup_state_code=get(0xA9)&15,
        crc_error_bits_a5=get(0xA5)&7,
        interpretation='88/89 bits 7:6: 0 hard shutdown, 1 soft shutdown, 2 enable, 3 reservado. O nome não é comando e não comprova tensão. CHIP_ENABLE em 96 é estado. CRC ativo não substitui verificação pós-recarga.')

def collect(link,directory):
    r=dict(kind='user_preparation_capture',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        complete=False,error=None,passes=[{},{}],status_before={},status_after={},programming_enabled=False,
        scope='USER 10–67: registradores ativos, duas passagens. Não é leitura direta da MTP nem imagem aprovada para gravação.')
    def read(reg):
        v=link.register_read(0x70,reg)
        if not v['pec_verified']:raise ValueError(f'PEC inválido em {reg:02X}')
        return v
    try:
        check(link,r);r['mapping']=map_interface(link,0x70,100)
        r['cml_before']=link.telemetry_read(0x70,0x7E)
        for reg in STATUS:r['status_before'][f'{reg:02X}']=read(reg)
        for p in r['passes']:
            for reg in range(0x10,0x68):p[f'{reg:02X}']=read(reg)
        for reg in STATUS:r['status_after'][f'{reg:02X}']=read(reg)
        r['cml_after']=link.telemetry_read(0x70,0x7E)
        r['changed_registers']=[key for key in r['passes'][0] if r['passes'][0][key]['value']!=r['passes'][1][key]['value']]
        r['status_decoded_before']=decode_status(r['status_before'])
        r['status_decoded_after']=decode_status(r['status_after'])
        r['status_changed_registers']=[key for key in r['status_before'] if r['status_before'][key]['value']!=r['status_after'][key]['value']]
        r['complete']=True
        r['stable_user']=not r['changed_registers']
        r['values']=r['passes'][1]
        r['sha256_user_pass2']=hashlib.sha256(bytes(r['values'][f'{reg:02X}']['value'] for reg in range(0x10,0x68))).hexdigest()
        r['user_pin_fields']=decode_user_pins(r['values'])
        r['warnings']=[]
        if not r['stable_user']:r['warnings'].append('USER mudou entre passagens; não consolidar como imagem estável.')
        if r['cml_before']['value_raw'] or r['cml_after']['value_raw']:r['warnings'].append('STATUS_CML não zerado.')
    except Exception as exc:r['error']=str(exc)
    r['report_path']=save_backup(r,directory)
    return r
