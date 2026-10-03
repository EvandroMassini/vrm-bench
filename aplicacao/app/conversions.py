"""Generic conversions. Scales, codes and labels come from the selected controller JSON."""
from .controller_store import current, field

def _tables():
    return current()['tables']

def _spec(symbol):
    return field(symbol)['conversion']

def byte(values, address):
    if not isinstance(values, dict):
        return None
    if isinstance(values.get(address), int):
        return values[address]
    item = values.get(f'{address:02X}')
    if isinstance(item, dict) and isinstance(item.get('value'), int):
        return item['value']
    if isinstance(item, int):
        return item
    return None

def bits(values, address, offset, length):
    raw = byte(values, address)
    if raw is None:
        return None
    return (raw >> (8 - offset - length)) & ((1 << length) - 1)

def phase_index(symbol):
    marker = symbol.find('PHASE')
    if marker < 0:
        return None
    digits = ''.join(ch for ch in symbol[marker + 5:] if ch.isdigit())
    return int(digits) if digits else None

def _loop(symbol):
    return 1 if 'LOOP_1' in symbol else 2 if 'LOOP_2' in symbol else None

def _phases(loop, values):
    where = _tables()['phase_count']
    code = bits(values, where['address'], where['offset'], where['length'])
    if code is None:
        return None
    table = _tables()['loop1_phases' if loop == 1 else 'loop2_phases']
    return table[code]

def _phase_code(symbol, values):
    item = field(symbol)
    return bits(values, item['address'], item['offset'], item['length'])

def _cumulative(symbol, values):
    series = _spec(symbol)['series']
    total = 0
    for name in series[:series.index(symbol) + 1]:
        code = _phase_code(name, values)
        if code is None:
            return None
        total += code
    return total

def _require(spec, values):
    req = spec.get('require')
    if not req:
        return True
    raw = byte(values, req['address'])
    return bool(raw is not None and raw & req['mask'])

def owns(symbol):
    try:
        field(symbol)
    except KeyError:
        return False
    return True

def editable(symbol, values):
    spec = _spec(symbol)
    if not spec.get('editable'):
        return False
    if spec['type'] == 'phase_current':
        return bool(_phases(spec['loop'], values))
    if spec['type'] in ('vid_offset', 'vboot'):
        return _require(spec, values)
    return True

def _fmt(number):
    return f'{number:.6f}'.rstrip('0').rstrip('.')

def numeric(symbol, code, values):
    if code is None or not owns(symbol):
        return None
    spec = _spec(symbol)
    kind = spec['type']
    if kind == 'loadline':
        return None if code == 0 else code * (spec['step_mohm'] / 1000)
    if kind == 'phase_current':
        count = _phases(spec['loop'], values)
        if not count or (spec.get('zero') and code == 0):
            return None
        return code * spec['amps_per_code'] * count
    if kind == 'lookup':
        return _tables()[spec['table']][code]
    if kind == 'linear':
        return spec['origin'] + spec['step'] * code
    if kind == 'phase_sum':
        total = _cumulative(symbol, values)
        return None if total is None else total * spec['amps']
    if kind == 'vid_offset' and _require(spec, values):
        signed = code if code < 8 else code - 16
        return (signed + 1) * spec['step_mv']
    if kind == 'vboot' and _require(spec, values) and spec['low'] <= code <= spec['high']:
        return (spec['anchor'] - code) * spec['step']
    if kind == 'frequency':
        return 1e6 / (code * spec['period_us']) if code else None
    if kind == 'temperature':
        return code + spec['base']
    if kind == 'temperature_plus':
        origin = spec['from']
        raw = byte(values, origin['address'])
        if raw is None:
            return None
        return code + ((raw >> origin['shift']) & origin['mask']) + spec['add']
    if kind == 'signed':
        sign = 1 << (spec['bits'] - 1)
        return code - (1 << spec['bits']) if code & sign else code
    return None

def _enum_text(spec, code):
    for option in spec['options']:
        if option['code'] == code:
            return option['text']
    return None

def display(symbol, code, values):
    if not owns(symbol) or code is None:
        return None
    spec = _spec(symbol)
    kind = spec['type']
    if kind == 'enum':
        text = _enum_text(spec, code)
        return text if text is not None else 'Conversão não validada'
    if kind == 'match':
        return spec['text'] if code == spec['code'] else spec['else']
    if kind == 'loadline':
        if code == 0:
            linear = 1000 // spec['step_mohm']
            return f'1 mΩ (código 0; o código linear de 1 mΩ é {linear})'
        return _fmt(numeric(symbol, code, values)).replace('.', ',') + ' mΩ'
    if kind == 'phase_current':
        if spec.get('zero') and code == 0:
            return spec['zero']
        count = _phases(spec['loop'], values)
        if count is None:
            return 'Depende da configuração das saídas (registro 14 ausente)'
        if count == 0:
            return '0 A para qualquer código positivo (loop com 0 fases)'
        return f'{int(numeric(symbol, code, values))} A'
    if kind == 'lookup':
        unit = field(symbol).get('unit') or ''
        return f"{_tables()[spec['table']][code]} {unit}".strip()
    if kind == 'linear':
        return _fmt(numeric(symbol, code, values)).replace('.', ',') + ' V'
    if kind == 'phase_sum':
        total = _cumulative(symbol, values)
        if total is None:
            return 'Depende das fases anteriores'
        return f'{total * spec["amps"]} A'
    if kind == 'phase_layout':
        return f'{_tables()["loop1_phases"][code]} + {_tables()["loop2_phases"][code]} fases'
    if kind == 'mode_pair':
        parts = [bits(values, item['address'], item['offset'], item['length']) for item in spec['bits']]
        if any(part is None for part in parts):
            return spec['missing']
        return spec['map'][','.join(str(part) for part in parts)]
    if kind == 'vid_offset':
        if not _require(spec, values):
            return 'Conversão não validada'
        return _fmt(numeric(symbol, code, values)).replace('.', ',') + ' mV'
    if kind == 'vboot':
        if not _require(spec, values):
            return 'Conversão não validada'
        if code < spec['low']:
            return spec['below']
        return _fmt(numeric(symbol, code, values)).replace('.', ',') + ' V'
    if kind == 'frequency':
        if not code:
            return 'Indefinido (período zero)'
        return _fmt(numeric(symbol, code, values)).replace('.', ',') + ' kHz'
    if kind == 'temperature':
        return f'{int(numeric(symbol, code, values))} °C'
    if kind == 'temperature_plus':
        number = numeric(symbol, code, values)
        if number is None:
            return 'Depende de TEMP_MAX (registro 32 ausente)'
        return f'{int(number)} °C'
    if kind == 'signed':
        return f'{int(numeric(symbol, code, values))} passos VID'
    return None

def _number(text):
    try:
        number = float(text.strip().replace(',', '.').split()[0])
    except (ValueError, IndexError):
        raise ValueError('Informe um número decimal, sem unidade.')
    if number != number or number in (float('inf'), float('-inf')):
        raise ValueError('Informe um número finito.')
    return number

def _enum_code(spec, text):
    key = ' '.join(text.strip().lower().split())
    for option in spec['options']:
        names = [option['text']] + option.get('aliases', [])
        if key in {' '.join(name.lower().split()) for name in names}:
            return option['code']
    choices = ', '.join(option['text'] for option in spec['options'])
    raise ValueError(f'Use um destes valores: {choices}.')

def encode(symbol, text, values):
    if not editable(symbol, values):
        raise ValueError('Conversão de escrita não validada para este parâmetro.')
    spec = _spec(symbol)
    kind = spec['type']
    if kind == 'enum':
        if spec.get('zero') and text.strip().lower() in ('desabilitado', 'disabled'):
            return 0
        return _enum_code(spec, text)
    if kind == 'phase_current' and spec.get('zero') and text.strip().lower() in ('desabilitado', 'disabled'):
        return 0
    if kind == 'signed':
        number = _number(text)
        limit = 1 << (spec['bits'] - 1)
        code = round(number)
        if abs(number - code) > 1e-6 or not -limit <= code <= limit - 1:
            raise ValueError(f'Use um inteiro entre −{limit} e {limit - 1}.')
        return code & ((1 << spec['bits']) - 1)
    number = _number(text)
    if kind == 'loadline':
        step = spec['step_mohm']
        thousandths = round(number * 1000)
        shown = _fmt(step / 1000).replace('.', ',')
        if abs(number * 1000 - thousandths) > 1e-4 or thousandths % step or not 1 <= thousandths // step <= 255:
            raise ValueError(f'Use passos de {shown} mΩ, entre {shown} e {_fmt(255 * step / 1000).replace(".", ",")} mΩ.')
        return thousandths // step
    if kind == 'phase_current':
        count = _phases(spec['loop'], values)
        unit = spec['amps_per_code'] * count
        code = round(number / unit)
        if abs(number - code * unit) > 1e-6 or not 0 <= code <= spec['max_code']:
            raise ValueError(f'Use múltiplos de {unit} A, entre 0 e {spec["max_code"] * unit} A.')
        return code
    if kind == 'lookup':
        table = _tables()[spec['table']]
        mv = round(number)
        if abs(number - mv) > 1e-6 or mv not in table:
            words = [str(item) for item in table]
            body = ', '.join(words[:-1]) + ' ou ' + words[-1]
            raise ValueError(f'Use um destes valores, em mV: {body}.')
        return table.index(mv)
    if kind == 'linear':
        scaled = round(number * 100000)
        origin = round(spec['origin'] * 100000)
        step = round(spec['step'] * 100000)
        delta = scaled - origin
        if abs(number * 100000 - scaled) > 1e-3 or delta % step or not 0 <= delta // step <= spec['max_code']:
            raise ValueError('Use 0,80625 a 2,49375 V em passos de 0,1125 V.')
        return delta // step
    if kind == 'phase_sum':
        total = round(number / spec['amps'])
        if abs(number - total * spec['amps']) > 1e-6 or total < 0:
            raise ValueError('Use um número par de ampères.')
        series = spec['series']
        index = series.index(symbol)
        previous = 0
        if index:
            previous = _cumulative(series[index - 1], values)
            if previous is None:
                raise ValueError('Fases anteriores ainda não foram lidas.')
        code = total - previous
        if not 0 <= code <= 15:
            raise ValueError('O acréscimo desta fase precisa ficar entre 0 e 30 A, em passos de 2 A.')
        return code
    if kind == 'vid_offset':
        raw = number / spec['step_mv'] - 1
        if not spec['min_n'] <= raw <= spec['max_n'] or abs(raw - round(raw)) > 1e-7:
            raise ValueError('Use passos de 6,25 mV, entre −43,75 e +50 mV.')
        return round(raw) & 15
    if kind == 'vboot':
        raw = spec['anchor'] - number / spec['step']
        if not spec['low'] <= raw <= spec['high'] or abs(raw - round(raw)) > 1e-7:
            raise ValueError('Use 0,0125 a 1,55 V em passos de 0,0125 V. Só entra em vigor na partida.')
        return round(raw)
    if kind == 'frequency':
        if not spec['min_khz'] <= number <= spec['max_khz']:
            raise ValueError('Frequência permitida: 200 a 2000 kHz.')
        code = round(1e6 / (number * spec['period_us']))
        actual = 1e6 / (code * spec['period_us'])
        if abs(actual - number) > 0.01:
            raise ValueError(f'Valor não representável. Use {actual:.4f} kHz (valor mais próximo).')
        return code
    if kind in ('temperature', 'temperature_plus'):
        if kind == 'temperature':
            base = spec['base']
        else:
            origin = spec['from']
            raw = byte(values, origin['address'])
            base = ((raw >> origin['shift']) & origin['mask']) + spec['add']
        code = number - base
        if abs(code - round(code)) > 1e-7:
            raise ValueError('Use uma temperatura inteira.')
        return round(code)
    raise ValueError('Conversão de escrita não validada para este parâmetro.')

def source(symbol):
    try:
        return field(symbol).get('source', '')
    except KeyError:
        return ''

def report_text(symbol, code, values):
    if code is None or not owns(symbol):
        return None
    text = display(symbol, code, values)
    return None if text is None else (text, source(symbol))

def _balance(gain):
    if gain is None:
        return 'Não lido'
    factor = 64 / (64 - gain)
    shown = f'{factor:.3f}'.rstrip('0').rstrip('.').replace('.', ',')
    if gain == 0:
        return '0 · igual a uma fase sem ganho'
    return f'{gain} · fator {shown} em relação a uma fase sem ganho'

def _per_phase_ocp(loop, values):
    fast_field = field(f'LOOP_{loop}_OCP_THR')
    slow_field = field(f'LOOP_{loop}_SLOW_IPH_MAX')
    fast = bits(values, fast_field['address'], fast_field['offset'], fast_field['length'])
    slow = bits(values, slow_field['address'], slow_field['offset'], slow_field['length'])
    fast_text = 'Não lido' if fast is None else f'{fast * 2} A'
    slow_text = 'Não lido' if slow is None else ('Desabilitado' if slow == 0 else f'{slow * 2} A')
    return fast_text, slow_text

def phase_rows(values):
    n1 = _phases(1, values)
    n2 = _phases(2, values)
    rows = []
    for item in _tables()['phase_gain']:
        number = item['phase']
        gain = bits(values, item['address'], item['offset'], 4)
        if n1 is None:
            loop, fast, slow = 'Aguardando leitura', '—', '—'
        elif number <= n1:
            loop, (fast, slow) = 'Loop 1', _per_phase_ocp(1, values)
        elif number <= n1 + (n2 or 0):
            loop, (fast, slow) = 'Loop 2', _per_phase_ocp(2, values)
        else:
            loop, fast, slow = 'Fora da configuração', '—', '—'
        rows.append((f'Fase {number}', loop, fast, slow, _balance(gain)))
    return rows

_chip = current()
LOOP1_PHASES = tuple(_chip['tables']['loop1_phases'])
LOOP2_PHASES = tuple(_chip['tables']['loop2_phases'])
RELATIVE_MV = tuple(_chip['tables']['relative_mv'])
PHASE_BITS = {item['symbol']: (item['address'], item['offset'], item['length'])
              for item in _chip['fields'] if item['conversion']['type'] == 'phase_sum'}
