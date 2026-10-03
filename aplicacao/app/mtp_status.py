"""Passive active-pointer reads only. No OTP_COMMAND, clock enable or reload."""
from datetime import datetime, timezone
from .parameters import save_backup
from .registers import map_interface
from .bus_health import check
from .controller_store import current
from .telemetry import cml_code

def _mtp():
    data = current().get('mtp')
    if not data or not data.get('indicators'):
        raise ValueError('O JSON selecionado não descreve os ponteiros de memória.')
    return data

def remaining(pointer, capacity, sentinel):
    if pointer == sentinel:
        return capacity
    if 0 <= pointer < capacity:
        return capacity - 1 - pointer
    return None

def decode(registers):
    if isinstance(registers, dict):
        values = {int(key): value for key, value in registers.items()}
    else:
        raise ValueError('Esperado o mapa dos registradores declarados no JSON.')
    rows = []
    for item in _mtp()['indicators']:
        raw = values[int(item['register'])]
        if type(raw) != int or not 0 <= raw <= 255:
            raise ValueError('Esperados bytes dos ponteiros')
        pointer = (raw >> int(item['shift'])) & int(item['mask'])
        capacity = int(item['capacity'])
        sentinel = int(item['sentinel'])
        left = remaining(pointer, capacity, sentinel)
        rows.append(dict(region=item['name'], pointer=pointer, remaining_indicated=left,
                         pointer_valid=left is not None, capacity_in_official_ui=capacity))
    return rows

def inspect(link, directory):
    data = _mtp()
    bus = current()['bus']
    pmbus = int(bus['pmbus'], 16)
    pointers = [int(item) for item in data['pointer_registers']]
    r = dict(kind='mtp_active_indicators', timestamp_utc=datetime.now(timezone.utc).isoformat(),
        complete=False, error=None, values={}, programming_enabled=False,
        limitation='Indicadores ativos declarados no JSON deste CI, sem recarga. Não comprovam integridade, imagem completa ou prontidão de programação.')
    try:
        check(link, r)
        r['mapping'] = map_interface(link, pmbus, bus['speed_khz'])
        r['cml_before'] = link.telemetry_read(pmbus, cml_code())
        for reg in pointers:
            v = link.register_read(pmbus, reg)
            if not v['pec_verified']:
                raise ValueError(f'PEC inválido em {reg:02X}')
            r['values'][f'{reg:02X}'] = v
        r['regions'] = decode({reg: r['values'][f'{reg:02X}']['value'] for reg in pointers})
        r['cml_after'] = link.telemetry_read(pmbus, cml_code())
        r['complete'] = True
        r['warnings'] = []
        if any(not x['pointer_valid'] for x in r['regions']):
            r['warnings'].append('Ponteiro fora dos estados interpretados pelo mapa; não calcular próximo slot.')
        if r['cml_before']['value_raw'] or r['cml_after']['value_raw']:
            r['warnings'].append('STATUS_CML não zerado; revisar antes de prosseguir.')
    except Exception as exc:
        r['error'] = str(exc)
    r['report_path'] = save_backup(r, directory)
    return r
