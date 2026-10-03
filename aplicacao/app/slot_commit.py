"""Count USER slots and commit exactly one. MFR is only reported."""
import hashlib
import re
from datetime import datetime, timezone
from .bus_health import check
from .config_dump import addresses, capture
from .controller_store import current
from .param_byte import load_baseline
from .parameters import save_backup
from .registers import map_interface
from .reload_mtp import masked_differences
from .verify_user import crc_flags
from .telemetry import cml_code

COMMAND = 'COMMIT 08 USER'

def user_plan(pointer):
    data = current().get('mtp')
    if not data:
        raise ValueError('O JSON selecionado não descreve os ponteiros de slot.')
    if not isinstance(pointer, int) or not 0 <= pointer <= 255:
        raise ValueError('Ponteiro USER inválido')
    mask = int(data['user_pointer_mask'])
    capacity = int(data['user_capacity'])
    sentinel = int(data['user_sentinel'])
    nibble = pointer & mask
    if nibble == sentinel:
        left = capacity
    elif nibble < capacity:
        left = capacity - 1 - nibble
    else:
        left = 0
    if left <= 0:
        return dict(nibble=nibble, left=0, index=None, opcode=None)
    index = capacity - left
    return dict(nibble=nibble, left=left, index=index, opcode=int(data.get('opcode_base', 64)) | index)

def mfr_left(pointer):
    item = next((row for row in (current().get('mtp') or {}).get('indicators') or [] if row.get('name') == 'MFR'), None)
    if item is None:
        raise ValueError('O JSON selecionado não descreve o ponteiro MFR.')
    bits = (pointer >> int(item['shift'])) & int(item['mask'])
    capacity, sentinel = int(item['capacity']), int(item['sentinel'])
    if bits == sentinel:
        return capacity
    if bits < capacity:
        return capacity - 1 - bits
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

def image_token(values, chosen=None):
    chosen = tuple(chosen) if chosen is not None else addresses()
    payload = ''.join(values[f'{address:02X}'] for address in chosen)
    return hashlib.sha256(payload.encode('ascii')).hexdigest()

def as_map(values, chosen=None):
    chosen = tuple(chosen) if chosen is not None else addresses()
    return {address: int(values[f'{address:02X}'], 16) for address in chosen}

def preview_changes(link, directory, read_map=None, baseline=None):
    current()
    if link.version != 16:
        raise ValueError(f'O Pico responde protocolo {link.version}. A leitura das diferenças usa o UF2 0.50, protocolo 16.')
    reference = load_baseline() if baseline is None else baseline
    result = dict(kind='mtp_change_preview', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  complete=False, error=None, command_sent=False, write_attempted=False, slot_commit=False,
                  scope='Lê a imagem ativa e lista o que difere da leitura anterior à alteração em RAM. Não grava slot.')
    try:
        check(link, result)
        image = (read_map or capture)(link, directory)
        result['stable'] = bool(image.get('stable'))
        result['txt_path'] = image.get('txt_path')
        result['user_sha256'] = image.get('user_sha256')
        if not image.get('stable') or not image.get('values'):
            raise ValueError('A leitura não ficou estável; nada foi preparado para gravação')
        rows = masked_differences(image['values'], reference)
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

def commit_user_slot(link,directory,read_map=None,require='match',image_token_expected=None,baseline=None):
    from .generic_operations import commit
    return commit(link,directory,read_map,require,image_token_expected,baseline)
