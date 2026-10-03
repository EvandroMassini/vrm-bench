"""Passive active-pointer reads only. No OTP_COMMAND, clock enable or reload."""
from datetime import datetime,timezone
from .parameters import save_backup
from .registers import map_interface
from .bus_health import check

def remaining(pointer,capacity,sentinel):
    if pointer==sentinel:return capacity
    if 0<=pointer<capacity:return capacity-1-pointer
    return None

def decode(a6,a7):
    if any(type(x)!=int or not 0<=x<=255 for x in (a6,a7)):raise ValueError('Esperados dois bytes')
    specs=(('TRIM',(a6>>3)&7,3,7),('USER',a7&15,9,15),('MFR',a6&7,3,7))
    return [dict(region=name,pointer=ptr,remaining_indicated=remaining(ptr,capacity,sentinel),
                 pointer_valid=remaining(ptr,capacity,sentinel) is not None,capacity_in_official_ui=capacity)
            for name,ptr,capacity,sentinel in specs]

def inspect(link,directory):
    r=dict(kind='mtp_active_indicators',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        complete=False,error=None,values={},programming_enabled=False,
        limitation='Indicadores ativos A6/A7, sem recarga OTP. Não comprovam integridade, imagem completa ou prontidão de programação.')
    try:
        check(link,r);r['mapping']=map_interface(link,0x70,100)
        r['cml_before']=link.telemetry_read(0x70,0x7E)
        for reg in (0xA6,0xA7):
            v=link.register_read(0x70,reg)
            if not v['pec_verified']:raise ValueError(f'PEC inválido em {reg:02X}')
            r['values'][f'{reg:02X}']=v
        r['regions']=decode(r['values']['A6']['value'],r['values']['A7']['value'])
        r['cml_after']=link.telemetry_read(0x70,0x7E)
        r['complete']=True
        r['warnings']=[]
        if any(not x['pointer_valid'] for x in r['regions']):r['warnings'].append('Ponteiro fora dos estados interpretados pelo mapa; não calcular próximo slot.')
        if r['cml_before']['value_raw'] or r['cml_after']['value_raw']:r['warnings'].append('STATUS_CML não zerado; revisar antes de prosseguir.')
    except Exception as exc:r['error']=str(exc)
    r['report_path']=save_backup(r,directory)
    return r
