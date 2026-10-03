from datetime import datetime,timezone
from .registers import map_interface
from .bus_health import check,explanation

def compare_paths(link,pmbus,direct,khz,registers,reference,cancelled,progress):
    if not registers or len(registers)>64 or any(not 0<=r<=255 for r in registers):raise ValueError('Lista inválida')
    if not reference.strip():raise ValueError('Informe a origem da lista.')
    result=dict(kind='interface_crosscheck',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        pmbus_address_7bit=pmbus,direct_i2c_address_7bit=direct,khz_nominal=khz,
        requested_registers=registers,reference=reference,rows=[],comparison=[],
        complete=False,cancelled=False,error=None,
        scope='Comparação parcial de registradores ativos; não é backup MTP. I²C direto sem PEC.')
    try:
        from .catalog import metadata
        result['register_catalog']=metadata(registers)
        check(link,result)
        if cancelled.is_set():result['cancelled']=True;return result
        result['mapping']=mapping=map_interface(link,pmbus,khz)
        if not mapping['direct_i2c_enabled'] or mapping['direct_i2c_address_7bit']!=direct:
            raise ValueError('Endereço I²C informado difere de D6 ou interface desabilitada. Nenhuma leitura direta realizada.')
        result['cml_before']=link.telemetry_read(pmbus,0x7E)
        for pass_number in (1,2):
            for register in registers:
                if cancelled.is_set():result['cancelled']=True;return result
                row=dict(pass_number=pass_number,register_hex=f'{register:02X}',status='pending')
                result['rows'].append(row)
                try:
                    row['pmbus']=link.register_read(pmbus,register)
                    if not row['pmbus'].get('pec_verified'):raise ValueError('PEC PMBus não confirmado')
                    value=link.read(direct,register)
                    row['direct']=dict(value=value,raw_hex=f'{value:02X}',pec_verified=None)
                    row.update(status='response',equal=value==row['pmbus']['value'])
                except Exception as exc:
                    row.update(status='error',error=str(exc));progress(row);raise
                progress(row)
        for i,register in enumerate(registers):
            first,second=result['rows'][i],result['rows'][i+len(registers)]
            values=[r[path]['value'] for r in (first,second) for path in ('pmbus','direct')]
            result['comparison'].append(dict(register_hex=f'{register:02X}',values_hex=[f'{v:02X}' for v in values],equal=len(set(values))==1))
        result['cml_after']=link.telemetry_read(pmbus,0x7E)
        result['all_equal']=all(r['equal'] for r in result['comparison'])
        result['complete']=True
    except Exception as exc:
        result['error']=str(exc);result['guidance']=explanation(exc)
    return result
