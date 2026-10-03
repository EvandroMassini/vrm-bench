"""Offline comparison of completed, internally consistent crosschecks."""
import json
from pathlib import Path
from datetime import datetime,timezone

def load_capture(path):
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if data.get('kind')!='interface_crosscheck' or data.get('source')!='Pico USB':
        raise ValueError('Selecione uma comparação PMBus × I²C obtida com Pico USB.')
    if not data.get('complete') or data.get('error') or data.get('cancelled'):
        raise ValueError('A captura deve estar completa, sem erro ou cancelamento.')
    registers=data.get('requested_registers',[])
    if not registers or len(set(registers))!=len(registers):raise ValueError('Lista de registradores inválida.')
    rows=data.get('rows',[])
    if len(rows)!=2*len(registers):raise ValueError('Número de leituras inconsistente.')
    values={}
    seen=set()
    for row in rows:
        reg=int(row['register_hex'],16);key=(row['pass_number'],reg)
        if key in seen or key[0] not in (1,2) or reg not in registers:raise ValueError('Passagens inconsistentes.')
        seen.add(key)
        pm,direct=row['pmbus'],row['direct']
        value=pm['value']
        if row.get('status')!='response' or pm.get('pec_verified') is not True or type(value)!=int or not 0<=value<=255:
            raise ValueError('Leitura inválida ou PEC não confirmado.')
        if value!=direct['value'] or int(pm['raw_hex'],16)!=value or int(direct['raw_hex'],16)!=value:
            raise ValueError('Divergência dentro de uma captura; analise-a antes de comparar sessões.')
        if reg in values and values[reg]!=value:raise ValueError('Passagens diferentes dentro da captura.')
        values[reg]=value
    model=data.get('mapping',{}).get('model_read',{})
    from .controller_store import model_hex
    if model.get('raw_hex')!=model_hex() or model.get('pec_verified') is not True:raise ValueError(f"Modelo {model_hex()} com PEC não confirmado.")
    return data,values

def compare_files(reference,current):
    if Path(reference).resolve()==Path(current).resolve():raise ValueError('Selecione dois arquivos distintos.')
    a,av=load_capture(reference);b,bv=load_capture(current)
    result=dict(kind='session_comparison',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        reference_file=str(reference),current_file=str(current),reference_timestamp=a.get('timestamp_utc'),
        current_timestamp=b.get('timestamp_utc'),rows=[],warnings=[],
        limitation='Comparação de arquivos. Não comprova ciclo de alimentação, identidade física da placa ou conteúdo da MTP.')
    for key in ('pmbus_address_7bit','direct_i2c_address_7bit','khz_nominal'):
        if a.get(key)!=b.get(key):result['warnings'].append(f'{key} difere: {a.get(key)} / {b.get(key)}')
    if a.get('timestamp_utc')==b.get('timestamp_utc'):result['warnings'].append('Mesmo timestamp: os arquivos podem ser cópias da mesma captura.')
    for reg in sorted(av.keys()|bv.keys()):
        old,new=av.get(reg),bv.get(reg)
        state='ausente na referência' if old is None else 'ausente na atual' if new is None else 'igual' if old==new else 'alterado'
        result['rows'].append(dict(register_hex=f'{reg:02X}',reference_hex=None if old is None else f'{old:02X}',current_hex=None if new is None else f'{new:02X}',state=state))
    result['all_equal']=all(r['state']=='igual' for r in result['rows'])
    result['changed_count']=sum(r['state']=='alterado' for r in result['rows'])
    result['missing_count']=sum(r['state'].startswith('ausente') for r in result['rows'])
    return result
