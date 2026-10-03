"""Compile declarative byte transactions; no controller-specific addresses."""
import copy
from .controller_store import current
from .profile_schema import require,validate

OPS={'assert':0,'temporary':1,'persistent':2,'command':3}

def compile_steps(profile,steps):
    validate(profile)
    result=[]
    for step in steps:
        row=[OPS[step['op']],step['register'],step['mask'],step['value'],step.get('delay_ms',2),step.get('poll_mask',0),step.get('poll_value',0),step.get('attempts',1)]
        if any(type(v) is not int or not 0<=v<=255 for v in row):raise ValueError('Transação não resolvida')
        if not row[2] or row[3]&~row[2] or not 1<=row[7]<=20:raise ValueError('Máscara/limite inválido')
        result.append(row)
    if not 0<len(result)<=64:raise ValueError('Transação excede 64 passos')
    return result

def execute(link,steps,profile=None):
    profile=copy.deepcopy(profile or current())
    if link.version!=16:raise ValueError('Atualize o Pico com o firmware 0.50 (protocolo 16).')
    rows=compile_steps(profile,steps)
    ident=profile['protocol']['identity'];address=int(profile['bus']['direct'],16)
    begin=f'TXBEGIN {address:02X} {ident["register"]:02X} {ident["mask"]:02X} {ident["value"]:02X} {len(rows):02X}'
    if link.request(begin)!='OK TXBEGIN':raise ValueError('Preparação rejeitada')
    for index,row in enumerate(rows):
        if link.request('TXSTEP '+' '.join(f'{v:02X}' for v in [index]+row))!='OK TXSTEP':raise ValueError('Passo rejeitado')
    import re
    response=link.request('TXRUN')
    match=re.fullmatch(r'OK TX (0[01]) ([0-9A-F]{2}) (0[01]) (0[01])',response)
    if not match:raise ValueError('Resultado da transação inválido; não repetir escrita')
    ok,failed,wrote,restored=[int(v,16) for v in match.groups()]
    return dict(complete=bool(ok and restored),restored=bool(restored),write_attempted=bool(wrote),failed_step=None if failed==255 else failed,
                error=None if ok and restored else 'Transação não confirmada; não repetir automaticamente. Consulte o passo e a restauração.',profile=profile['id'])

def guards(profile):
    return [dict(op='assert',**g) for g in profile['protocol']['guards']]

def recipe(link,name,extra=(),variables=None):
    profile=copy.deepcopy(require(name));steps=guards(profile)+list(extra)
    for step in profile['recipes'][name]:
        item=copy.deepcopy(step)
        if isinstance(item['value'],str):item['value']=(variables or {})[item['value']]
        steps.append(item)
    return execute(link,steps,profile)

def change(link,address,expected,target,mask=None):
    profile=require('parameters')
    if mask is None:
        mask=profile['parameters']['write_masks'].get(str(address),0)
    mask=int(mask or 0)&255
    if not mask or (expected^target)&~mask:raise ValueError('Alteração fora da máscara permitida no JSON')
    return execute(link,guards(profile)+[dict(op='assert',register=address,mask=255,value=expected),dict(op='persistent',register=address,mask=mask,value=target&mask)])
