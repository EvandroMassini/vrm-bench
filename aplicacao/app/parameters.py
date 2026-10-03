"""Limited active-register backup; never a complete MTP image."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .bus_health import check
from .registers import map_interface

def loops(value):
    if not isinstance(value,int) or not 0<=value<=255:raise ValueError('Byte inválido')
    return [dict(loop=i+1,raw_hex=f'{n:X}',signed_code=n if n<8 else n-16)
            for i,n in enumerate((value>>4,value&15))]

_overwrite_prompt=None

def set_overwrite_prompt(prompt):
    global _overwrite_prompt
    previous=_overwrite_prompt
    _overwrite_prompt=prompt
    return previous

def _write_json(path,data,exclusive):
    with path.open('x' if exclusive else 'w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())

def _next_name(path):
    stem,suffix,parent=path.stem,path.suffix,path.parent
    number=2
    while True:
        candidate=parent/f'{stem}_{number}{suffix}'
        if not candidate.exists():return candidate
        number+=1

def save_backup(data,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/('backup_offsets_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')+'.json')
    asked=False
    while True:
        try:_write_json(path,data,True);return str(path)
        except FileExistsError:
            if not asked and _overwrite_prompt and _overwrite_prompt(path):
                _write_json(path,data,False);return str(path)
            asked=True
            path=_next_name(path)

def snapshot(link,directory):
    r=dict(kind='offset_snapshot',timestamp_utc=datetime.now(timezone.utc).isoformat(),
           scope='Somente registros ativos 14 e 26; não é backup completo nem MTP.',values={})
    check(link,r)
    r['mapping']=m=map_interface(link,0x70,100)
    if not m['direct_i2c_enabled'] or m['direct_i2c_address_7bit']!=8:raise ValueError('Alvo incompatível com I²C 08.')
    for reg in (0x14,0x26):
        v=link.register_read(0x70,reg)
        if not v['pec_verified']:raise ValueError('PEC inválido; backup não confirmado.')
        r['values'][f'{reg:02X}']=v
    r['loops']=loops(r['values']['26']['value'])
    r['backup_path']=save_backup(r,directory)
    return r

def backup_before_test(result,directory):
    # Persist the current baseline, not an older preview. Failure aborts before USB command.
    data=dict(kind='before_offset_experiment',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        scope='Backup parcial do registro ativo 26; não é imagem MTP.',
        register_hex='26',baseline=result['baseline'],mapping=result['mapping'],
        proposed_hex='EF',restore_hex='FF',hold_requested_ms=result.get('hold_requested_ms',0))
    result['backup_path']=save_backup(data,directory)
