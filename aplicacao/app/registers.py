"""Explicit register captures; no inferred register map or MTP backup claims."""
import re
from datetime import datetime,timezone
from .transport import crc8

def parse_registers(text):
    result=[]
    for token in text.replace(',',' ').split():
        if not re.fullmatch(r'(?:0[xX])?[0-9A-Fa-f]{1,2}',token):
            raise ValueError('Use bytes HEX separados por espaço; intervalos não são aceitos.')
        value=int(token,16)
        if value not in result:result.append(value)
    if not result or len(result)>64:raise ValueError('Informe de 1 a 64 registradores documentados.')
    return result

def decode_register(response,address):
    m=re.fullmatch(r'OK BLOCK 01 ([0-9A-F]{2}) ([0-9A-F]{2})',response)
    if not m:raise ValueError('Resposta de registrador malformada')
    value,received=int(m[1],16),int(m[2],16)
    from .controller_store import current
    command=current()['protocol']['register_access']['read_command']
    expected=crc8(bytes([address<<1,command,address<<1|1,value]))
    if received!=expected:raise ValueError(f'PEC {command:02X} inválido: {received:02X}, esperado {expected:02X}')
    return dict(value=value,raw_hex=m[1],pec_verified=True,pec_received=m[2],pec_expected=f'{expected:02X}')

def identify(link,address,khz):
    if link.version<6:raise ValueError('Atualize o UF2 para v0.6 (protocolo 6).')
    link.set_speed(khz)
    from .controller_store import current
    identity=current()['identity']
    model=link.pm_read(address,identity['model_command'],True,False)
    if model['raw_hex']!=identity['model_hex'] or not model['pec_verified']:raise ValueError(f"Modelo {identity['model_hex']}h com PEC não confirmado")
    return model

def map_interface(link,address,khz):
    model=identify(link,address,khz)
    from .controller_store import current
    spec=current()['protocol']['mapping']
    raw=link.telemetry_read(address,spec['command'])
    value=raw['value_raw']
    return dict(kind='interface_mapping',timestamp_utc=datetime.now(timezone.utc).isoformat(),
                pmbus_address_7bit=address,model_read=model,d6=raw,
                direct_i2c_enabled=bool(value&spec['enabled_mask']),direct_i2c_address_7bit=(value&spec['address_mask'])>>spec['address_shift'],
                limitation=f'Interpretação do comando {spec["command"]:02X} pelo perfil; não escreve endereço nem testa a interface direta')

def capture(link,address,khz,registers,reference,cancelled,progress):
    if not reference.strip():raise ValueError('Informe a origem da lista de registradores.')
    if not registers or len(registers)>64 or any(not 0<=r<=255 for r in registers):raise ValueError('Lista inválida')
    result=dict(kind='active_register_capture',timestamp_utc=datetime.now(timezone.utc).isoformat(),
                pmbus_address_7bit=address,khz_nominal=khz,reference=reference,
                requested_registers=registers,passes=[[],[]],comparison=[],complete=False,cancelled=False,error=None,
                scope='Registradores ativos selecionados; não é backup completo nem leitura direta da MTP',
                mechanism='Leitura do registrador pelo comando declarado no perfil; altera apenas o ponteiro de leitura')
    try:
        from .catalog import metadata
        from .telemetry import cml_code
        from .controller_store import current
        access=current()['protocol']['register_access']
        result['mechanism']=f'SET_POINTER {access["pointer_command"]:02X} com PEC + leitura {access["read_command"]:02X} com PEC; altera apenas o ponteiro de leitura'
        result['register_catalog']=metadata(registers)
        from .bus_health import check,explanation
        check(link,result)
        result['model_read']=identify(link,address,khz)
        result['cml_before']=link.telemetry_read(address,cml_code())
        for pass_index in range(2):
            for reg in registers:
                if cancelled.is_set():result['cancelled']=True;return result
                row=dict(pass_number=pass_index+1,register_hex=f'{reg:02X}',timestamp_utc=datetime.now(timezone.utc).isoformat())
                try:row.update(status='response',**link.register_read(address,reg))
                except Exception as exc:
                    row.update(status='error',error=str(exc))
                    result['passes'][pass_index].append(row);progress(row)
                    raise
                result['passes'][pass_index].append(row);progress(row)
        for a,b in zip(*result['passes']):
            result['comparison'].append(dict(register_hex=a['register_hex'],first=a['raw_hex'],second=b['raw_hex'],equal=a['value']==b['value']))
        result['cml_after']=link.telemetry_read(address,cml_code())
        result['complete']=True
        result['all_equal']=all(row['equal'] for row in result['comparison'])
    except Exception as exc:
        result['error']=str(exc)
        result['guidance']=explanation(exc)
    return result
