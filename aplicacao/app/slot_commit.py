"""Count Comanche USER slots and commit exactly one. MFR is only reported."""
import hashlib
import re
from datetime import datetime, timezone
from .bus_health import check
from .config_dump import ADDRESSES, capture
from .param_byte import load_baseline
from .parameters import save_backup
from .registers import map_interface
from .reload_mtp import masked_differences
from .verify_user import crc_flags

COMMAND = 'COMMIT 08 USER'

def user_plan(pointer):
    if not isinstance(pointer, int) or not 0 <= pointer <= 255:
        raise ValueError('Ponteiro USER inválido')
    nibble = pointer & 0x0F
    if nibble == 15:
        left = 9
    elif nibble < 9:
        left = 8 - nibble
    else:
        left = 0
    if left <= 0:
        return dict(nibble=nibble, left=0, index=None, opcode=None)
    index = 9 - left
    return dict(nibble=nibble, left=left, index=index, opcode=0x40 | index)

def mfr_left(pointer):
    bits = pointer & 0x07
    if bits == 7:
        return 3
    if bits < 3:
        return 2 - bits
    return 0

def decode(line):
    match = re.fullmatch(
        r'OK COMMIT ((?:[0-9A-F]{2} ){20}[0-9A-F]{2})', line)
    if not match:
        raise ValueError('Resposta COMMIT inválida; estado desconhecido')
    values = [int(item, 16) for item in match.group(1).split()]
    (shut, pointer, left, index, opcode, clock_ok, opcode_sent, program_ok, d0_program,
     reload_sent, reload_ok, d0_reload, a5, pointer_after, left_after, sample10, sample26,
     clock_ok_final, en_ok, fa, fb) = values
    plan = user_plan(pointer)
    if plan['left'] != left or plan['index'] != index or plan['opcode'] != opcode:
        raise ValueError('O opcode USER não confere com o ponteiro lido')
    if not 0x40 <= opcode <= 0x48:
        raise ValueError('Opcode USER fora de 40h–48h')
    restored = bool(clock_ok_final and en_ok and fa == 0x88 and fb == 0x88)
    after = user_plan(pointer_after)
    return dict(shutdown_confirmed=bool(shut), pointer_before_hex=f'{pointer:02X}',
                user_left_before=left, slot_index=index, opcode_hex=f'{opcode:02X}',
                clock_write_confirmed=bool(clock_ok), opcode_sent=bool(opcode_sent),
                program_finished=bool(program_ok), command_after_program_hex=f'{d0_program:02X}',
                reload_sent=bool(reload_sent), reload_finished=bool(reload_ok),
                command_after_reload_hex=f'{d0_reload:02X}', crc=crc_flags(a5),
                pointer_after_hex=f'{pointer_after:02X}', user_left_after=left_after,
                user_left_after_check=after['left'], pointer_advanced=after['nibble'] == index,
                sample10_hex=f'{sample10:02X}', sample26_hex=f'{sample26:02X}',
                clock_restored=bool(clock_ok_final), enable_restored=bool(en_ok),
                enable88_hex=f'{fa:02X}', enable89_hex=f'{fb:02X}', restored=restored)

def _image_ok(image, baseline):
    if not image.get('stable') or not image.get('values'):
        return False, None
    rows = masked_differences(image['values'], baseline)
    return not rows, rows

def image_token(values):
    payload = ''.join(values[f'{address:02X}'] for address in ADDRESSES)
    return hashlib.sha256(payload.encode('ascii')).hexdigest()

def as_map(values):
    return {address: int(values[f'{address:02X}'], 16) for address in ADDRESSES}

def preview_changes(link, directory, read_map=None):
    if link.version != 15:
        raise ValueError(f'O Pico responde protocolo {link.version}. A leitura das diferenças usa o UF2 0.26, protocolo 15.')
    result = dict(kind='mtp_change_preview', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  complete=False, error=None, command_sent=False, write_attempted=False, slot_commit=False,
                  scope='Lê a imagem ativa e lista o que difere do arquivo desta placa. Não grava slot.')
    try:
        check(link, result)
        image = (read_map or capture)(link, directory)
        result['stable'] = bool(image.get('stable'))
        result['txt_path'] = image.get('txt_path')
        result['user_sha256'] = image.get('user_sha256')
        if not image.get('stable') or not image.get('values'):
            raise ValueError('A leitura não ficou estável; nada foi preparado para gravação')
        rows = masked_differences(image['values'], load_baseline())
        result['differences'] = rows
        result['difference_count'] = len(rows)
        result['image_token'] = image_token(image['values'])
        result['complete'] = True
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        try:
            result['report_path'] = save_backup(result, directory)
        except OSError as exc:
            result['save_error'] = str(exc)
    return result

def commit_user_slot(link, directory, read_map=None, require='match', image_token_expected=None):
    if link.version != 15:
        raise ValueError(f'O Pico responde protocolo {link.version}. Grave o UF2 0.26 e conecte de novo antes de gravar o slot.')
    result = dict(kind='mtp_user_slot', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  complete=False, error=None, command_sent=False, write_attempted=False,
                  programming_enabled=False, slot_commit=False,
                  scope='Conta os slots no nibble de A7h e, se houver algum, grava um único slot USER com a imagem já presente na RAM. Restaura 71h, 88h e 89h no Pico. Não grava MFR e não escreve 99h.')
    reader = read_map or capture
    try:
        check(link, result)
        result['mapping'] = mapping = map_interface(link, 0x70, 100)
        if not mapping['direct_i2c_enabled'] or mapping['direct_i2c_address_7bit'] != 8:
            raise ValueError('Alvo diferente de I²C 08')
        result['cml_before'] = link.telemetry_read(0x70, 0x7E)
        if result['cml_before']['value_raw'] != 0:
            raise ValueError('CML não zerado; gravação bloqueada')
        baseline = load_baseline()
        before = reader(link, directory)
        result['image_before'] = dict(stable=before.get('stable'), txt_path=before.get('txt_path'),
                                       user_sha256=before.get('user_sha256'), error=before.get('error'))
        matched, rows = _image_ok(before, baseline)
        result['image_before_matches'] = matched
        result['differences'] = rows or []
        result['difference_count'] = 0 if rows is None else len(rows)
        if require == 'match' and not matched:
            result['mismatches_before'] = (rows or [])[:20]
            raise ValueError('A imagem ativa não coincide com o arquivo desta placa; slot não gravado')
        if require == 'changed':
            if not before.get('stable') or not before.get('values'):
                raise ValueError('A leitura não ficou estável; slot não gravado')
            token = image_token(before['values'])
            result['image_token'] = token
            if token != image_token_expected:
                raise ValueError('A imagem mudou desde a leitura das diferenças. Leia de novo; slot não gravado')
            if matched or not rows:
                raise ValueError('A imagem é igual ao arquivo desta placa. Não vou gastar outro slot com a mesma imagem.')
        result['backup_path'] = save_backup(result, directory)
        result['command_sent'] = True
        try:
            line = link.request(COMMAND)
        except RuntimeError as exc:
            text = str(exc)
            empty = re.fullmatch(r'ERR COMMIT_NOSLOT ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2})', text)
            if empty:
                pointer, left, mfr, mfr_count = [int(item, 16) for item in empty.groups()]
                result.update(pointer_before_hex=f'{pointer:02X}', user_left_before=left,
                              mfr_pointer_hex=f'{mfr:02X}', mfr_left=mfr_count, write_attempted=False)
                raise ValueError(f'Nenhum slot USER restante. Ponteiro A7h={pointer:02X}. Nada foi escrito.') from exc
            if re.fullmatch(r'ERR COMMIT_(MODEL|MODE_VALUE( [0-9A-F]{2})?|BASELINE [0-9A-F]{2} [0-9A-F]{2}|CLOCK [0-9A-F]{2}|INDEX|PRECHECK [0-9A-F]{2} (IDLE_BEFORE|POINTER|READ|WRITE|STOP) -?\d+)', text):
                result['write_attempted'] = False
            raise
        parsed = decode(line)
        result.update(parsed)
        result['write_attempted'] = True
        result['slot_commit'] = parsed['opcode_sent']
        result['crc']['note'] = 'Bits 2, 1 e 0 de A5 lidos depois da recarga 20h que segue a gravação do slot.'
        if not parsed['restored']:
            raise ValueError('Restauração do enable ou do relógio não confirmada')
        if parsed['opcode_sent'] and not parsed['program_finished']:
            raise ValueError('O comando do slot foi enviado e não terminou. Não repetir: o slot pode ter sido consumido.')
        if parsed['program_finished'] and parsed['reload_finished'] and parsed['pointer_advanced'] and not parsed['crc']['active_error']:
            after = reader(link, directory)
            result['image_after'] = dict(stable=after.get('stable'), txt_path=after.get('txt_path'),
                                          user_sha256=after.get('user_sha256'), error=after.get('error'))
            expected = baseline if require == 'match' else as_map(before['values'])
            matched_after, rows_after = _image_ok(after, expected)
            result['mismatch_count'] = 0 if rows_after is None else len(rows_after)
            result['mismatches'] = (rows_after or [])[:20]
            result['image_matches_expected'] = matched_after
            result['image_matches_board_file'] = matched_after if require == 'match' else False
            result['slots_consumed'] = parsed['user_left_before'] - parsed['user_left_after_check']
            result['complete'] = bool(matched_after and result['slots_consumed'] == 1)
        if parsed['opcode_sent'] and not result['complete']:
            result['warning'] = 'Não repetir esta gravação. O opcode pode ter consumido um slot mesmo quando a verificação seguinte não fechou.'
    except Exception as exc:
        result['error'] = str(exc)
        if result['command_sent'] and not result.get('restored', False) and result.get('write_attempted') is not False:
            result['guidance'] = 'Não repetir. Se 88 e 89 não estiverem em 88, desligue a placa.'
    finally:
        try:
            result['report_path'] = save_backup(result, directory)
        except OSError as exc:
            result['save_error'] = str(exc)
    return result
