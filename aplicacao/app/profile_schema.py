"""Versioned controller contract. Values are data; recipes cannot execute Python."""
import math

class ProfileError(ValueError): pass

def validate(p):
    def need(ok,msg):
        if not ok: raise ProfileError(msg)
    def integer(v,lo=0,hi=255): return type(v) is int and lo<=v<=hi
    need(isinstance(p,dict),'O perfil deve ser um objeto')
    need(p.get('schema_version')==1,'schema_version deve ser 1')
    need(isinstance(p.get('id'),str) and bool(p['id'].strip()),'id obrigatório')
    for key in ('identity','bus','protocol','capabilities','telemetry','dump','parameters','fields','recipes','tables','verify'):
        need(key in p,f'Seção obrigatória: {key}')
    for key in ('pmbus','direct'):
        try: address=int(p['bus'][key],16)
        except (ValueError,TypeError,KeyError): raise ProfileError(f'bus.{key}: endereço HEX inválido')
        need(8<=address<=119 and address!=12,f'bus.{key}: endereço reservado')
    pr=p['protocol'];need(pr['minimum']==16,'Protocolo mínimo deve ser 16')
    need(pr['direct_access']=='i2c_register8','Interface direta não suportada')
    access=pr['register_access'];need(access['kind']=='pmbus_pointer8','Acesso a registradores não suportado')
    for key in ('pointer_command','read_command'):need(integer(access[key]),f'{key} inválido')
    ident=pr['identity']
    for key in ('register','mask','value'):need(integer(ident[key]),f'Identidade: {key} inválido')
    need(ident['mask']>0 and not ident['value']&~ident['mask'],'Máscara de identidade inválida')
    need(integer(pr['identity_read']['bytes'],0,32),'Comprimento de identidade inválido')
    need(integer(p['identity']['model_command']),'Comando de identidade inválido')
    need(all(type(v) is bool for v in p['capabilities'].values()),'Capacidades devem ser booleanas')
    fields=p['fields'];need(isinstance(fields,list),'fields deve ser uma lista')
    symbols=set()
    conversions={'enum','match','mode_pair','phase_layout','signed','phase_current','temperature_plus','temperature','lookup','loadline','linear','vid_offset','phase_sum','frequency','vboot'}
    for f in fields:
        need(f['symbol'] not in symbols,'Símbolo duplicado: '+f['symbol']);symbols.add(f['symbol'])
        need(integer(f['address']) and integer(f['offset'],0,7) and integer(f['length'],1,8) and f['offset']+f['length']<=8,'Campo fora do byte: '+f['symbol'])
        cv=f['conversion'];need(cv['type'] in conversions,'Conversão desconhecida: '+cv['type'])
        codes=[x['code'] for x in cv.get('options',[]) if 'code' in x]
        need(all(integer(x,0,(1<<f['length'])-1) for x in codes),'Código enum fora do campo')
        need(len(codes)==len(set(codes)),'Código enum duplicado')
    for f in fields:
        for ref in f['conversion'].get('series',[]):need(ref in symbols,'Referência inexistente: '+ref)
    cmds=p['telemetry']['commands'];codes=[x['code'] for x in cmds]
    need(len(codes)==len(set(codes)),'Comando de telemetria duplicado')
    for c in cmds:
        need(integer(c['code']) and integer(c['bytes'],1,4),'Comando/comprimento inválido')
        need(c['decoder'] in ('raw','linear11','linear16','unsigned','signed','scaled'),'Decodificador desconhecido')
        need(c.get('byteorder') in ('little','big'),'Ordem de bytes inválida')
        if c['decoder']=='linear11':need(c['bytes']==2,'Linear11 exige 2 bytes')
        for key in ('scale','offset'):
            if key in c:need(isinstance(c[key],(int,float)) and math.isfinite(c[key]),'Escala inválida')
    for key in ('cml_command','mode_command'):need(p['telemetry'][key] in codes,f'{key} ausente dos comandos')
    addrs=p['dump']['addresses'];need(len(addrs)==len(set(addrs)) and all(integer(x) for x in addrs),'Mapa de dump inválido')
    for key,value in p['dump']['mask_overrides'].items():need(integer(int(key)) and integer(value),'Máscara de dump inválida')
    params=p['parameters'];need(integer(params['writable_start']) and integer(params['writable_end']) and params['writable_start']<=params['writable_end'],'Faixa de escrita inválida')
    for key,value in params['write_masks'].items():
        need(integer(int(key),params['writable_start'],params['writable_end']) and integer(value,1,255) and int(key) not in params['blocked'],'Permissão de escrita inválida')
    for guard in pr['guards']:
        need(all(integer(guard[k]) for k in ('register','mask','value')) and guard['mask']>0 and not guard['value']&~guard['mask'],'Precondição inválida')
    for name,steps in p['recipes'].items():
        need(isinstance(steps,list) and 0<len(steps)<=50,'Receita vazia ou longa demais')
        modified=set()
        for s in steps:
            need(s['op'] in ('assert','temporary','persistent','command'),'Operação desconhecida')
            need(integer(s['register']) and integer(s['mask'],1,255),'Registrador/máscara inválidos')
            dynamic=s['value']=='$opcode'
            need((dynamic and name=='commit' and s['op']=='command') or (integer(s['value']) and not s['value']&~s['mask']),'Valor de receita inválido')
            need(integer(s.get('delay_ms',2),0,255) and integer(s.get('attempts',1),1,20),'Tempo de receita inválido')
            if s['op']=='command':
                need(s['mask']==255 and integer(s['poll_mask'],1,255) and integer(s['poll_value']) and not s['poll_value']&~s['poll_mask'],'Polling inválido')
            elif s['op']!='assert':
                need(s['register'] not in modified,'Registrador temporário repetido');modified.add(s['register'])
    cap=p['capabilities']
    for name in ('commit','reload','enable'):
        need(not cap.get(name) or name in p['recipes'],f'{name} habilitado sem receita')
    if cap.get('slots') or cap.get('commit'):
        mtp=p.get('mtp');need(isinstance(mtp,dict),'Slots exigem seção mtp')
        for key in ('user_pointer_register','user_pointer_mask','user_sentinel','opcode_base'):need(integer(mtp[key]),f'mtp.{key} inválido')
        need(integer(mtp['user_capacity'],1,16),'Capacidade inválida')
        need(mtp['user_sentinel']>mtp['user_capacity']-1 and (mtp['user_sentinel']&mtp['user_pointer_mask'])==mtp['user_sentinel'],'Sentinela inválida')
        need((mtp['opcode_base'] & (mtp['user_capacity']-1))==0,'Opcode se sobrepõe ao índice')
    return p

def require(capability,profile=None):
    if profile is None:
        from .controller_store import current
        profile=current()
    if not profile['capabilities'].get(capability,False):
        raise ProfileError(profile.get('capability_notes',{}).get(capability,f'Função {capability} não declarada para {profile["id"]}.'))
    return profile
