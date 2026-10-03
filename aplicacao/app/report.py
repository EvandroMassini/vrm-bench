"""Read-only consolidated report. No write plan is derived from reference files."""
from datetime import datetime,timezone
from .field_map import FIELDS
from .parameters import save_backup
from .registers import map_interface
from .bus_health import check
from .core import compare
from .engineering import convert
from .controller_store import current
REGISTERS=tuple(current()['report']['registers'])

def analyze(values,reference=()):
    refs={e.address:e for e in reference};rows=[]
    for f in FIELDS:
        key=f"{f['address']:02X}";v=values.get(key)
        raw=v['value'] if v is not None else None
        if raw is not None and (type(raw)!=int or not 0<=raw<=255):raise ValueError('Byte inválido no JSON')
        shift=8-f['offset']-f['length'];mask=((1<<f['length'])-1)<<shift
        ref=refs.get(f['address']);refvalue=None if ref is None else (ref.value&mask)>>shift
        actual=None if raw is None else (raw&mask)>>shift
        state='Sem referência' if ref is None else ('Não lido' if raw is None else compare(type(ref)(ref.address,ref.value,ref.mask&mask),raw))
        symbol=f['symbol'];loop='1' if 'LOOP_1' in symbol else ('2' if 'LOOP_2' in symbol else 'Comum / não atribuído')
        engineering,source=convert(symbol,actual,values)
        rows.append(dict(engineering=engineering,conversion_source=source,register=key,loop=loop,field=symbol,bits=f"{7-f['offset']}:{shift}",value=actual,reference=refvalue,comparison=state))
    return rows

def collect(link,directory,reference=()):
    r=dict(kind='parameter_report',timestamp_utc=datetime.now(timezone.utc).isoformat(),values={},complete=False,error=None,
           scope='23 registros ativos; backup parcial, não MTP. Conversões de configuração não são medições.',
           field_source='PowIRCenter 8712 / ComancheRegisterClass; extração estática, posições MSB. Escalas físicas não validadas.')
    try:
        bus=current()['bus'];pmbus=int(bus['pmbus'],16);direct=int(bus['direct'],16)
        check(link,r);r['mapping']=m=map_interface(link,pmbus,bus['speed_khz'])
        if not m['direct_i2c_enabled'] or m['direct_i2c_address_7bit']!=direct:raise ValueError(f"Endereço direto não é {bus['direct']}")
        r['cml_before']=link.telemetry_read(pmbus,0x7E)
        for reg in REGISTERS:
            value=link.register_read(pmbus,reg)
            if not value['pec_verified']:raise ValueError(f'PEC inválido em {reg:02X}')
            r['values'][f'{reg:02X}']=value
        r['cml_after']=link.telemetry_read(pmbus,0x7E)
        r['complete']=True
    except Exception as exc:r['error']=str(exc)
    r['reference_entries']=[dict(address=e.address,value=e.value,mask=e.mask) for e in reference]
    r['rows']=analyze(r['values'],reference)
    r['backup_path']=save_backup(r,directory)
    return r
