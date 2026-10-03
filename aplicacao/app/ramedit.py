"""Restricted RAM apply/restore. Independent fresh baseline, persistent prewrite backup."""
import re
from datetime import datetime,timezone
from .parameters import save_backup
from .registers import map_interface
from .bus_health import check

def change(link,directory,restore=False):
    if link.version not in (11,12):raise ValueError('Exige firmware 0.18 ou 0.21, protocolo 11 ou 12.')
    expected,target=(0xEF,0xFF) if restore else (0xFF,0xEF)
    r=dict(kind='ram_offset_change',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        operation='restore' if restore else 'apply',expected_hex=f'{expected:02X}',target_hex=f'{target:02X}',
        complete=False,error=None,command_sent=False,write_attempted=False,
        scope='Somente RAM, registro 26; nenhuma programação MTP. EF permanece até restaurar; fechar o aplicativo não restaura.')
    try:
        check(link,r);r['mapping']=m=map_interface(link,0x70,100)
        if not m['direct_i2c_enabled'] or m['direct_i2c_address_7bit']!=8:raise ValueError('Alvo diferente de 08')
        r['cml_before']=link.telemetry_read(0x70,0x7E)
        if not restore and r['cml_before']['value_raw']!=0:raise ValueError('CML não zerado; aplicação bloqueada')
        r['baseline']=b=link.register_read(0x70,0x26)
        if not b['pec_verified']:raise ValueError('PEC inválido')
        if b['value']==target:
            r.update(complete=True,no_change_needed=True,final_hex=f'{target:02X}');return r
        if b['value']!=expected:raise ValueError('26 diferente de FF/EF esperado; nenhuma escrita')
        try:r['backup_path']=save_backup(r,directory)
        except OSError as exc:
            if not restore:raise
            r['save_error']=str(exc)  # Do not block a return to FF because storage is unavailable.
        r['command_sent']=True;r['write_attempted']=None
        response=link.request(f'RAMSET 08 26 {expected:02X} {target:02X}')
        m=re.fullmatch(r'OK RAMSET (0[01]) (0[01]) (0[01]) ([0-9A-F]{2}) ([0-9A-F]{2})',response)
        if not m:raise ValueError('Resposta RAMSET inválida; estado desconhecido')
        applied,rollback,final_ok,last,mode=[int(x,16) for x in m.groups()]
        r.update(write_attempted=True,applied=bool(applied),rollback_attempted=bool(rollback),
                 final_read_ok=bool(final_ok),final_hex=f'{last:02X}',mode_hex=f'{mode:02X}')
        r['after']=after=link.register_read(0x70,0x26)
        r['cml_after']=link.telemetry_read(0x70,0x7E)
        r['complete']=bool(applied and final_ok and last==target and after['pec_verified'] and after['value']==target)
        if not r['complete']:raise ValueError('Alteração não confirmada; confira byte final e rollback no relatório')
        if r['cml_after']['value_raw']!=0:r['warning']='STATUS_CML não zerado após operação; não ampliar alterações.'
    except Exception as exc:
        r['error']=str(exc)
        if re.fullmatch(r'ERR (RAMSET_(MODE|STALE)|RAMTEST_MODEL|RAMTEST_PRECHECK [0-9A-F]{2} (IDLE_BEFORE|POINTER|READ|STOP) -?\d+)',str(exc)):
            r['write_attempted']=False
        if r['command_sent']:
            r['guidance']='Não repetir aplicação. Se EF estiver ativo, use Restaurar FF; se o estado não puder ser confirmado, desligue a placa.'
    finally:
        try:r['report_path']=save_backup(r,directory)
        except OSError as exc:r['save_error']=str(exc)
    return r
