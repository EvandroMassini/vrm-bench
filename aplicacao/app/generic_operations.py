"""Application workflows over profile-described, locally restored transactions."""
from datetime import datetime,timezone
from .controller_store import current
from .profile_schema import require
from . import transactions as tx
from .bus_health import check
from .registers import map_interface
from .telemetry import cml_code
from .parameters import save_backup

def result(kind):
    return dict(kind=kind,timestamp_utc=datetime.now(timezone.utc).isoformat(),complete=False,error=None,
                command_sent=False,write_attempted=False,slot_commit=False,profile=current()['id'])

def preflight(link,r,capability):
    p=require(capability)
    if link.version!=16:raise ValueError('Atualize o Pico para protocolo 16.')
    check(link,r)
    r['mapping']=m=map_interface(link,int(p['bus']['pmbus'],16),p['bus']['speed_khz'])
    if not m['direct_i2c_enabled'] or m['direct_i2c_address_7bit']!=int(p['bus']['direct'],16):raise ValueError('Interface direta não corresponde ao JSON selecionado')
    cml=link.telemetry_read(int(p['bus']['pmbus'],16),cml_code())
    if not cml['pec_verified'] or cml['value_raw']:raise ValueError('Estado de comunicação não permite escrita')
    return p

def read(link,reg):
    v=link.register_read(int(current()['bus']['pmbus'],16),reg)
    if not v['pec_verified']:raise ValueError('Integridade do registrador não confirmada')
    return v['value']

def change_byte(link,directory,address,target,baseline,mask=None):
    r=result('parameter_byte')
    try:
        preflight(link,r,'parameters')
        expected=baseline[address];live=read(link,address)
        r.update(address_hex=f'{address:02X}',target_hex=f'{target:02X}',live_before_hex=f'{live:02X}')
        if live==target:r.update(complete=True,no_change_needed=True);return r
        if live!=expected:raise ValueError('Valor mudou desde a leitura; atualize a leitura antes de escrever')
        r['backup_path']=save_backup(dict(r,baseline=baseline),directory)
        r['command_sent']=True;r['write_attempted']=None
        r.update(tx.change(link,address,expected,target,mask))
        if r['complete']:
            final=read(link,address);r['final_hex']=f'{final:02X}'
            if final!=target:raise ValueError('Leitura final difere do valor solicitado')
            cml=link.telemetry_read(int(current()['bus']['pmbus'],16),cml_code())
            if cml['value_raw']:r['warning']='Estado de comunicação alterado; não continue as escritas.'
    except Exception as exc:r.update(complete=False,error=str(exc))
    finally:r['report_path']=save_backup(r,directory)
    return r

def commit(link,directory,read_map=None,mode='match',token=None,baseline=None):
    from .config_dump import capture
    from .slot_commit import user_plan,image_token,as_map
    from .reload_mtp import masked_differences
    r=result('mtp_user_slot');reader=read_map or capture
    try:
        p=preflight(link,r,'commit')
        if baseline is None:raise ValueError('Gravação exige a leitura original desta sessão')
        before=reader(link,directory)
        if not before.get('stable') or not before.get('values'):raise ValueError('Imagem de RAM incompleta ou instável')
        differences=masked_differences(before['values'],baseline)
        if mode=='changed':
            if not differences or image_token(before['values'])!=token:raise ValueError('Imagem mudou ou não há diferenças; obtenha nova confirmação')
        elif mode!='match' or differences:raise ValueError('Imagem não coincide com a referência da sessão')
        mtp=p['mtp'];pointer=read(link,mtp['user_pointer_register']);plan=user_plan(pointer)
        r.update(user_left_before=plan['left'],pointer_before_hex=f'{pointer:02X}',image_before=before)
        if plan['left']<=0:raise ValueError('Nenhum slot USER disponível')
        r['backup_path']=save_backup(r,directory)
        extra=[dict(op='assert',register=mtp['user_pointer_register'],mask=255,value=pointer)]
        r['command_sent']=True;r['write_attempted']=None
        r.update(tx.recipe(link,'commit',extra,{'$opcode':plan['opcode']}))
        r['slot_commit']=r['write_attempted'] # Conservative: cannot rule out consuming a slot on a failure.
        if not r['complete']:return r
        after_pointer=read(link,mtp['user_pointer_register']);after_plan=user_plan(after_pointer)
        r.update(user_left_after=after_plan['left'],pointer_after_hex=f'{after_pointer:02X}',slots_consumed=plan['left']-after_plan['left'])
        if (after_pointer&mtp['user_pointer_mask'])!=plan['index'] or r['slots_consumed']!=1:raise ValueError('Avanço do ponteiro não confirmado; não repetir')
        v=p['verify'];flags=read(link,v['crc_register']);r['crc_hex']=f'{flags:02X}'
        if flags&v['crc_mask']:raise ValueError('Flag CRC ativa após gravação/recarga')
        after=reader(link,directory);r['image_after']=after
        if not after.get('stable') or masked_differences(after['values'],as_map(before['values'])):raise ValueError('Imagem após recarga não confere')
        r['complete']=True
    except Exception as exc:r.update(complete=False,error=str(exc))
    finally:
        if r['command_sent'] and not r['complete']:r['warning']='Não repetir: um slot pode ter sido consumido. Consulte ponteiro e restauração.'
        r['report_path']=save_backup(r,directory)
    return r

def reload_image(link,directory,read_map=None):
    from .config_dump import capture
    r=result('mtp_reload_read')
    try:
        p=preflight(link,r,'reload');r['backup_path']=save_backup(r,directory)
        r['command_sent']=True;r['write_attempted']=None;r.update(tx.recipe(link,'reload'))
        r['reload_confirmed']=r['complete']
        if r['complete']:
            v=p['verify'];r['crc_hex']=f"{read(link,v['crc_register']):02X}"
            if int(r['crc_hex'],16)&v['crc_mask']:raise ValueError('CRC ativo após recarga')
            r['image']= (read_map or capture)(link,directory)
            r['complete']=bool(r['image'].get('stable'))
    except Exception as exc:r.update(complete=False,error=str(exc))
    finally:r['report_path']=save_backup(r,directory)
    return r

def enable(link,before_send=None,hold=False):
    r=result('software_enable_experiment')
    try:
        p=preflight(link,r,'enable')
        if hold:raise ValueError('Este perfil oferece apenas o ensaio breve; pausa prolongada não declarada.')
        r['baseline']={f"{s['register']:02X}":read(link,s['register']) for s in p['recipes']['enable'] if s['op']=='temporary'}
        r['hold_requested_ms']=0
        if before_send:before_send(r)
        r['command_sent']=True;r['write_attempted']=None;r.update(tx.recipe(link,'enable'))
        r['change_confirmed']=r['complete'];r['restoration_confirmed']=r['restored']
    except Exception as exc:r.update(complete=False,error=str(exc))
    return r
