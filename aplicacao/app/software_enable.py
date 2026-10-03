"""Software chip-enable legend and one reversible soft-shutdown experiment."""
import re
from datetime import datetime, timezone
from .bus_health import check, explanation
from .registers import map_interface

CODES = {0: 'Hard shutdown', 1: 'Soft shutdown', 2: 'Enable', 3: 'Reservado'}
BASELINE = 0x88
SOFT = 0x48

def describe(value):
    if not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError('Byte inválido')
    code = (value >> 6) & 3
    return dict(raw_hex=f'{value:02X}', code=code, name=CODES[code], preserved_low_bits_hex=f'{value & 0x3F:02X}')

def pin_bit(value, offset):
    return (value >> (7 - offset)) & 1

def decode_user_pins(values):
    def byte(reg):
        return values[f'{reg:02X}']['value']
    return dict(
        second_enable_pin_select=pin_bit(byte(0x42), 1),
        second_enable_from_pin=pin_bit(byte(0x4C), 1),
        source='USER ativo. Offset contado a partir do MSB, como no PowIRCenter. Não é comando.')

def decode(response):
    pattern = r'OK ENSOFT' + r' ([0-9A-F]{2})' * 17
    m = re.fullmatch(pattern, response)
    if not m:
        raise ValueError('Resposta ENSOFT inválida; restauração não confirmada.')
    nums = [int(x, 16) for x in m.groups()]
    # w1 w2 r1 c88 r2 c89 r96 p96 ra9 pa9 s1 s2 f1 o88 f2 o89 mode
    if any(x not in (0, 1) for x in (nums[0], nums[1], nums[2], nums[4], nums[6], nums[8], nums[10], nums[11], nums[12], nums[14])):
        raise ValueError('Flags ENSOFT inválidos; restauração não confirmada.')
    w1, w2, r1, c88, r2, c89, r96, p96, ra9, pa9, s1, s2, f1, o88, f2, o89, mode = nums
    changed = bool(w1 and w2 and r1 and r2 and c88 == SOFT and c89 == SOFT)
    restored = bool(s1 and s2 and f1 and f2 and o88 == BASELINE and o89 == BASELINE)
    return dict(
        write88_ack=bool(w1), write89_ack=bool(w2),
        read88_ok=bool(r1), changed88_hex=f'{c88:02X}',
        read89_ok=bool(r2), changed89_hex=f'{c89:02X}',
        status96_read_ok=bool(r96), status96_hex=f'{p96:02X}',
        statusA9_read_ok=bool(ra9), statusA9_hex=f'{pa9:02X}',
        restore88_ack=bool(s1), restore89_ack=bool(s2),
        final88_read_ok=bool(f1), final88_hex=f'{o88:02X}',
        final89_read_ok=bool(f2), final89_hex=f'{o89:02X}',
        mode_hex=f'{mode:02X}',
        change_confirmed=changed, restoration_confirmed=restored)

def _reg(link, reg):
    value = link.register_read(0x70, reg)
    if not value['pec_verified'] or value['value'] not in range(256):
        raise ValueError(f'PEC inválido em {reg:02X}; nenhuma escrita realizada.')
    return value

def experiment(link, before_send=None, hold=False):
    if link.version not in (12, 13, 14, 15):
        raise ValueError('O religamento das saídas existe nos protocolos 12 a 15. O Pico atual deve estar no protocolo 15.')
    result = dict(
        kind='software_enable_experiment', timestamp_utc=datetime.now(timezone.utc).isoformat(),
        complete=False, error=None, command_sent=False, write_attempted=False,
        restoration_required=False, restoration_confirmed=None, change_confirmed=None,
        hold_requested_ms=10000 if hold else 0, programming_enabled=False,
        pmbus_address_7bit=0x70, direct_i2c_address_7bit=8,
        baseline_hex='88', soft_hex='48', code_from=2, code_to=1, code_restored=2,
        registers=('88', '89'),
        legend=CODES,
        scope='Ensaio RAM: bits 7:6 de 88 e 89, código 2 para 1 e de volta a 2. Sem hard shutdown, OPERATION ou MTP. Tensão não é medida pelo teste.')
    try:
        check(link, result)
        result['mapping'] = mapping = map_interface(link, 0x70, 100)
        if not mapping['direct_i2c_enabled'] or mapping['direct_i2c_address_7bit'] != 8:
            raise ValueError('D6 incompatível com o alvo fixo 08.')
        result['cml_before'] = cml = link.telemetry_read(0x70, 0x7E)
        if cml['value_raw'] != 0:
            raise ValueError('STATUS_CML não está zerado; teste não iniciado.')
        result['baseline'] = {f'{reg:02X}': _reg(link, reg) for reg in (0x88, 0x89, 0x96, 0xA9)}
        for reg in (0x88, 0x89):
            if result['baseline'][f'{reg:02X}']['value'] != BASELINE:
                raise ValueError(f'{reg:02X} não é 88; nenhuma escrita realizada.')
        result['baseline_decoded'] = {key: describe(item['value']) for key, item in result['baseline'].items() if key in ('88', '89')}
        if before_send is not None:
            before_send(result)
        result['command_sent'] = True
        result['write_attempted'] = None
        result['restoration_required'] = None
        command = 'ENHOLD 08 88 89 88 48 10000 RESTORE' if hold else 'ENSOFT 08 88 89 88 48 RESTORE'
        result.update(decode(link.request(command)))
        result['hold_completed'] = bool(hold and result['change_confirmed'])
        result['write_attempted'] = True
        result['restoration_required'] = True
        result['during_status'] = dict(
            register_96=describe_status96(result['status96_hex']) if result['status96_read_ok'] else None,
            register_A9=result['statusA9_hex'] if result['statusA9_read_ok'] else None,
            note='Leitura I²C direta imediatamente antes da restauração. Interprete 96/A9 como efeito do código 1 somente quando change_confirmed for verdadeiro.')
        if not result['restoration_confirmed']:
            raise ValueError('Restauração NÃO confirmada. Desligue a alimentação da placa e não repita o teste.')
        after = {f'{reg:02X}': _reg(link, reg) for reg in (0x88, 0x89)}
        result['after'] = after
        if any(after[key]['value'] != BASELINE for key in after):
            result['restoration_confirmed'] = False
            raise ValueError('Verificação PMBus da restauração falhou. Desligue a placa.')
        result['cml_after'] = link.telemetry_read(0x70, 0x7E)
        result['complete'] = True
        if not result['change_confirmed']:
            result['guidance'] = 'Restauração confirmada, mas 88 e 89 não ficaram em 48 ao mesmo tempo. O código 1 não foi comprovado. Não repetir em sequência.'
    except Exception as exc:
        result['error'] = str(exc)
        result['guidance'] = explanation(exc)
        text = str(exc)
        prewrite = re.fullmatch(r'ERR (BUS_BUSY|ENSOFT_MODEL|ENSOFT_BASELINE ([0-9A-F]{2}) ([0-9A-F]{2})|ENSOFT_MODE_VALUE ([0-9A-F]{2}))', text)
        detail = re.fullmatch(r'ERR ENSOFT_PRECHECK ([0-9A-F]{2}) (IDLE_BEFORE|POINTER|READ|STOP|WRITE) (-?\d+)', text)
        if result['command_sent'] and detail:
            result['write_attempted'] = False
            result['restoration_required'] = False
            result['precheck_failure'] = dict(register_hex=detail[1], stage=detail[2], sdk_code=int(detail[3]))
            result['guidance'] = f'Teste interrompido antes da escrita. Restauração não necessária. Registro {detail[1]}: falha em {detail[2]}, código {detail[3]}.'
        elif result['command_sent'] and prewrite:
            result['write_attempted'] = False
            result['restoration_required'] = False
            result['guidance'] = 'Teste interrompido antes da escrita. Nenhum valor de configuração foi alterado; restauração não necessária.'
        elif result['command_sent'] and result['restoration_confirmed'] is None:
            result['guidance'] += ' Estado da restauração desconhecido. Desligue a placa; não repita automaticamente.'
    return result

def describe_status96(raw_hex):
    value = int(raw_hex, 16)
    return dict(raw_hex=raw_hex, loop1_chip_enable_bit=(value >> 5) & 1, loop2_chip_enable_bit=(value >> 4) & 1,
                note='Estado lido, não comando. Enable em 1 não comprova regulação; 0 não comprova ausência de tensão.')
