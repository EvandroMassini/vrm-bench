"""Restricted RAM apply/restore. Independent fresh baseline, persistent prewrite backup."""
import re
from datetime import datetime, timezone
from .parameters import save_backup
from .registers import map_interface
from .bus_health import check
from .controller_store import current
from .telemetry import cml_code

def change(link, directory, restore=False):
    probe = current().get('ram_probe')
    if not probe:
        raise ValueError('O JSON selecionado não descreve o ensaio de RAM.')
    bus = current()['bus']
    pmbus, direct, speed = int(bus['pmbus'], 16), int(bus['direct'], 16), int(bus['speed_khz'])
    register, original, test = int(probe['register']), int(probe['original']), int(probe['test'])
    if link.version not in (11, 12):
        raise ValueError('Exige firmware 0.18 ou 0.21, protocolo 11 ou 12.')
    expected, target = (test, original) if restore else (original, test)
    r = dict(kind='ram_offset_change', timestamp_utc=datetime.now(timezone.utc).isoformat(),
        operation='restore' if restore else 'apply', expected_hex=f'{expected:02X}', target_hex=f'{target:02X}',
        complete=False, error=None, command_sent=False, write_attempted=False,
        scope=f'Somente RAM, registro {register:02X} do CI selecionado; nenhuma programação MTP. O byte de teste permanece até restaurar; fechar o aplicativo não restaura.')
    try:
        check(link, r)
        r['mapping'] = m = map_interface(link, pmbus, speed)
        if not m['direct_i2c_enabled'] or m['direct_i2c_address_7bit'] != direct:
            raise ValueError(f'Alvo diferente de {direct:02X}')
        r['cml_before'] = link.telemetry_read(pmbus, cml_code())
        if not restore and r['cml_before']['value_raw'] != 0:
            raise ValueError('CML não zerado; aplicação bloqueada')
        r['baseline'] = b = link.register_read(pmbus, register)
        if not b['pec_verified']:
            raise ValueError('PEC inválido')
        if b['value'] == target:
            r.update(complete=True, no_change_needed=True, final_hex=f'{target:02X}')
            return r
        if b['value'] != expected:
            raise ValueError(f'{register:02X} diferente do byte esperado pelo ensaio; nenhuma escrita')
        try:
            r['backup_path'] = save_backup(r, directory)
        except OSError as exc:
            if not restore:
                raise
            r['save_error'] = str(exc)
        r['command_sent'] = True
        r['write_attempted'] = None
        response = link.request(f'RAMSET {direct:02X} {register:02X} {expected:02X} {target:02X}')
        matched = re.fullmatch(r'OK RAMSET (0[01]) (0[01]) (0[01]) ([0-9A-F]{2}) ([0-9A-F]{2})', response)
        if not matched:
            raise ValueError('Resposta RAMSET inválida; estado desconhecido')
        applied, rollback, final_ok, last, mode = [int(x, 16) for x in matched.groups()]
        r.update(write_attempted=True, applied=bool(applied), rollback_attempted=bool(rollback),
                 final_read_ok=bool(final_ok), final_hex=f'{last:02X}', mode_hex=f'{mode:02X}')
        r['after'] = after = link.register_read(pmbus, register)
        r['cml_after'] = link.telemetry_read(pmbus, cml_code())
        r['complete'] = bool(applied and final_ok and last == target and after['pec_verified'] and after['value'] == target)
        if not r['complete']:
            raise ValueError('Alteração não confirmada; confira byte final e rollback no relatório')
        if r['cml_after']['value_raw'] != 0:
            r['warning'] = 'STATUS_CML não zerado após operação; não ampliar alterações.'
    except Exception as exc:
        r['error'] = str(exc)
        if re.fullmatch(r'ERR (RAMSET_(MODE|STALE)|RAMTEST_MODEL|RAMTEST_PRECHECK [0-9A-F]{2} (IDLE_BEFORE|POINTER|READ|STOP) -?\d+)', str(exc)):
            r['write_attempted'] = False
        if r['command_sent']:
            r['guidance'] = f'Não repetir aplicação. Se {test:02X} estiver ativo, restaure {original:02X}; se o estado não puder ser confirmado, desligue a placa.'
    finally:
        try:
            r['report_path'] = save_backup(r, directory)
        except OSError as exc:
            r['save_error'] = str(exc)
    return r
