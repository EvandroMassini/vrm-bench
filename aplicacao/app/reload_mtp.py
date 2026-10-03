"""Comanche MTP reload and read. Does not commit a slot."""
import re
from datetime import datetime, timezone
from .bus_health import check
from .config_dump import ADDRESSES, capture, mask_of
from .param_byte import load_baseline
from .parameters import save_backup
from .registers import map_interface
from .verify_user import crc_flags

COMMAND = 'RELOAD 08 71 20 24 D0 20'
BAXTER_CLOCK = 0x99
COMANCHE_CLOCK = 0x71
OTP_COMMAND = 0xD0

def decode(line):
    match = re.fullmatch(
        r'OK RELOAD ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) '
        r'([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) '
        r'([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2})',
        line)
    if not match:
        raise ValueError('Resposta RELOAD inválida; estado desconhecido')
    shut, clock_ok, clock_seen, cmd_ok, d0, a5, sample10, sample26, clock_restore, clock_final_ok, clock_final, en_ok, fa, fb = [
        int(item, 16) for item in match.groups()]
    restored = bool(clock_final == 0x20 and en_ok and fa == 0x88 and fb == 0x88)
    return dict(shutdown_confirmed=bool(shut), clock_write_confirmed=bool(clock_ok),
                clock_seen_hex=f'{clock_seen:02X}', command_write_confirmed=bool(cmd_ok),
                command_after_hex=f'{d0:02X}', crc=crc_flags(a5),
                sample10_hex=f'{sample10:02X}', sample26_hex=f'{sample26:02X}',
                clock_restore_attempted=bool(clock_restore), clock_final_read_ok=bool(clock_final_ok),
                clock_final_hex=f'{clock_final:02X}', enable_restored=bool(en_ok),
                enable88_hex=f'{fa:02X}', enable89_hex=f'{fb:02X}', restored=restored,
                reload_confirmed=bool(shut and clock_ok and cmd_ok and restored))

def masked_differences(live_hex, baseline):
    rows = []
    for address in ADDRESSES:
        live = int(live_hex[f'{address:02X}'], 16)
        mask = mask_of(address)
        expected = baseline[address]
        if (live ^ expected) & mask:
            rows.append(dict(register_hex=f'{address:02X}', file_hex=f'{expected:02X}',
                             live_hex=f'{live:02X}', mask_hex=f'{mask:02X}'))
    return rows

def reload_and_read(link, directory, read_map=None):
    if link.version not in (14, 15):
        raise ValueError(f'O Pico responde protocolo {link.version}. A recarga existe nos protocolos 14 e 15.')
    result = dict(kind='mtp_reload_read', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  complete=False, error=None, command_sent=False, write_attempted=False,
                  programming_enabled=False, slot_commit=False,
                  baxter_clock_hex=f'{BAXTER_CLOCK:02X}', comanche_clock_hex=f'{COMANCHE_CLOCK:02X}',
                  command_register_hex=f'{OTP_COMMAND:02X}', command_byte_hex='20',
                  scope='Recarga Comanche: 24h em 71h e 20h em D0h, com as saídas em código 1 e restauração local. Não usa o relógio Baxter 99h e não grava slot.')
    try:
        check(link, result)
        result['mapping'] = mapping = map_interface(link, 0x70, 100)
        if not mapping['direct_i2c_enabled'] or mapping['direct_i2c_address_7bit'] != 8:
            raise ValueError('Alvo diferente de I²C 08')
        result['cml_before'] = link.telemetry_read(0x70, 0x7E)
        if result['cml_before']['value_raw'] != 0:
            raise ValueError('CML não zerado; recarga bloqueada')
        result['backup_path'] = save_backup(result, directory)
        result['command_sent'] = True
        result['write_attempted'] = None
        parsed = decode(link.request(COMMAND))
        result.update(parsed)
        result['crc']['note'] = 'Bits 2, 1 e 0 de A5 lidos depois do comando 20h e antes de restaurar 71h. Qualquer 1 é erro de CRC Comanche.'
        result['write_attempted'] = True
        if not parsed['restored']:
            raise ValueError('Restauração do enable ou do relógio não confirmada')
        if parsed['reload_confirmed']:
            image = (read_map or (lambda link, directory: capture(link, directory, address_list=ADDRESSES)))(link, directory)
            result['image'] = dict(stable=image.get('stable'), txt_path=image.get('txt_path'),
                                    user_sha256=image.get('user_sha256'), error=image.get('error'))
            if image.get('stable') and image.get('values'):
                rows = masked_differences(image['values'], load_baseline())
                result['mismatch_count'] = len(rows)
                result['mismatches'] = rows[:20]
                result['image_matches_board_file'] = not rows
        if parsed['restored'] and not parsed['reload_confirmed']:
            result['warning'] = 'As saídas e o relógio voltaram. A recarga não foi confirmada e nenhum slot foi gravado.'
        result['complete'] = bool(parsed['reload_confirmed'] and result.get('image_matches_board_file'))
        if parsed['reload_confirmed'] and not result['complete']:
            result['warning'] = 'A recarga terminou e os enables voltaram. A imagem lida depois não coincidiu com o arquivo desta placa, ou as duas passagens divergiram.'
    except Exception as exc:
        result['error'] = str(exc)
        if re.fullmatch(r'ERR RELOAD_(MODEL|MODE_VALUE( [0-9A-F]{2})?|BASELINE [0-9A-F]{2} [0-9A-F]{2}|CLOCK [0-9A-F]{2}|PRECHECK [0-9A-F]{2} (IDLE_BEFORE|POINTER|READ|WRITE|STOP) -?\d+)', str(exc)):
            result['write_attempted'] = False
        if result['command_sent'] and not result.get('restored', False):
            result['guidance'] = 'Não repetir. Se 88 e 89 não estiverem em 88, desligue a placa.'
    finally:
        try:
            result['report_path'] = save_backup(result, directory)
        except OSError as exc:
            result['save_error'] = str(exc)
    return result
