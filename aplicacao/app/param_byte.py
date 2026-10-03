"""Write one active IR3567B byte and restore it to this board's saved file. No MTP."""
import re
from datetime import datetime, timezone
from pathlib import Path
from .bus_health import check
from .config_dump import mask_of
from .core import parse_config
from .parameters import save_backup
from .registers import map_interface

from .controller_store import current
_parameters = current()['parameters']
BASELINE_PATH = Path(__file__).resolve().parents[1] / 'samples' / current()['dump']['baseline_file']
BLOCKED = frozenset(_parameters['blocked'])

def load_baseline(path=None):
    entries = parse_config(Path(path or BASELINE_PATH).read_text(encoding='utf-8-sig'))
    return {entry.address: entry.value for entry in entries}

def writable(values):
    params = current()['parameters']
    blocked = frozenset(params['blocked'])
    return [(address, values[address]) for address in sorted(values)
            if params['writable_start'] <= address <= params['writable_end'] and mask_of(address) == 0xFF and address not in blocked]

def command(address, expected, target):
    params = current()['parameters']
    blocked = frozenset(params['blocked'])
    if address in blocked or not params['writable_start'] <= address <= params['writable_end'] or mask_of(address) != 0xFF:
        raise ValueError('Registrador bloqueado. Máscara 00, relógio OTP, enable e personalidade não são escritos.')
    if not 0 <= expected <= 255 or not 0 <= target <= 255:
        raise ValueError('Byte inválido')
    if expected == target:
        raise ValueError('O valor novo é igual ao byte do arquivo.')
    return f"PBYTE {params['direct_address']:02X} {address:02X} {expected:02X} {target:02X}"

def change_byte(link, directory, address, target, baseline):
    if link.version not in (13, 14, 15):
        raise ValueError('Grave o UF2 0.26, protocolo 15, antes de alterar um parâmetro. Os protocolos 13 e 14 também aceitam este byte.')
    file_value = baseline[address]
    r = dict(kind='parameter_byte', timestamp_utc=datetime.now(timezone.utc).isoformat(),
             address_hex=f'{address:02X}', file_hex=f'{file_value:02X}', target_hex=f'{target:02X}',
             operation='restore' if target == file_value else 'apply',
             complete=False, error=None, command_sent=False, write_attempted=False,
             programming_enabled=False,
             scope='Um byte de RAM no mapa 10h–90h. O arquivo desta placa é a origem. MTP não é programada. Fechar o aplicativo não restaura.')
    try:
        command(address, file_value if target != file_value else 0, target if target != file_value else 1)
        check(link, r)
        r['mapping'] = mapping = map_interface(link, 0x70, 100)
        if not mapping['direct_i2c_enabled'] or mapping['direct_i2c_address_7bit'] != 8:
            raise ValueError('Alvo diferente de I²C 08')
        r['cml_before'] = link.telemetry_read(0x70, 0x7E)
        if target != file_value and r['cml_before']['value_raw'] != 0:
            raise ValueError('CML não zerado; aplicação bloqueada')
        live = link.register_read(0x70, address)
        if not live['pec_verified']:
            raise ValueError('PEC inválido')
        r['live_before_hex'] = f'{live["value"]:02X}'
        if live['value'] == target:
            r.update(complete=True, no_change_needed=True, final_hex=f'{target:02X}')
            return r
        if target != file_value and live['value'] != file_value:
            raise ValueError('O byte ativo não é o do arquivo. Restaure antes de aplicar outro valor.')
        sent = command(address, live['value'], target)
        try:
            r['backup_path'] = save_backup(r, directory)
        except OSError as exc:
            if target != file_value:
                raise
            r['save_error'] = str(exc)
        r['command_sent'] = True
        r['write_attempted'] = None
        response = link.request(sent)
        match = re.fullmatch(r'OK PBYTE ([0-9A-F]{2}) (0[01]) (0[01]) (0[01]) ([0-9A-F]{2}) ([0-9A-F]{2})', response)
        if not match:
            raise ValueError('Resposta PBYTE inválida; estado desconhecido')
        echoed, applied, rollback, final_ok, last, mode = [int(item, 16) for item in match.groups()]
        if echoed != address:
            raise ValueError('A resposta citou outro registrador')
        r.update(write_attempted=True, applied=bool(applied), rollback_attempted=bool(rollback),
                 final_read_ok=bool(final_ok), final_hex=f'{last:02X}', mode_hex=f'{mode:02X}')
        after = link.register_read(0x70, address)
        r['after'] = after
        r['cml_after'] = link.telemetry_read(0x70, 0x7E)
        r['complete'] = bool(applied and final_ok and last == target and after['pec_verified'] and after['value'] == target)
        if not r['complete']:
            raise ValueError('Alteração não confirmada; confira o byte final no relatório')
        if r['cml_after']['value_raw'] != 0:
            r['warning'] = 'STATUS_CML não zerado após a operação; não altere outro registrador.'
    except Exception as exc:
        r['error'] = str(exc)
        if re.fullmatch(r'ERR (PBYTE_(BLOCKED|SAME|STALE|MODE)|RAMTEST_MODEL|RAMTEST_PRECHECK [0-9A-F]{2} (IDLE_BEFORE|POINTER|READ|WRITE|STOP) -?\d+)', str(exc)):
            r['write_attempted'] = False
        if r['command_sent'] and not r.get('complete'):
            r['guidance'] = 'Não repetir a aplicação. Use Restaurar byte do arquivo. Se o estado não puder ser lido, desligue a placa.'
    finally:
        try:
            r['report_path'] = save_backup(r, directory)
        except OSError as exc:
            r['save_error'] = str(exc)
    return r
