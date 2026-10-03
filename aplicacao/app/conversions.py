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
    return field(symbol).get('phase')

def _loop(symbol):
    return field(symbol).get('loop')

def _phases(loop, values):
    where = _tables()['phase_count']
    code = bits(values, where['address'], where['offset'], where['length'])
    if code is None:return None
    item=next(x for x in current()['loops'] if x['id']==f'loop{loop}')
    return _tables()[item['phase_table']][code]


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
        signed = code if code < (1<<(spec['bits']-1)) else code - (1<<spec['bits'])
        return (signed + spec['bias']) * spec['step_mv']
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
        return _fmt(numeric(symbol, code, values)).replace('.', ',') + ' '+field(symbol).get('unit','')
    if kind == 'phase_sum':
        total = _cumulative(symbol, values)
        if total is None:
            return 'Depende das fases anteriores'
        return f'{total * spec["amps"]} A'
    if kind == 'phase_layout':
        return ' + '.join(str(_tables()[t][code]) for t in spec['tables'])+' fases'
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
        return _fmt(numeric(symbol, code, values)).replace('.', ',') + ' '+field(symbol).get('unit','')
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
            raise ValueError(f"Use {spec['origin']} a {spec['origin']+spec['max_code']*spec['step']} em passos de {spec['step']}.")
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
        if not 0 <= code <= spec['max_code']:
            raise ValueError(f"Acréscimo de 0 a {spec['max_code']*spec['amps']} A em passos de {spec['amps']}.")
        return code
    if kind == 'vid_offset':
        raw = number / spec['step_mv'] - spec['bias']
        if not spec['min_n'] <= raw <= spec['max_n'] or abs(raw - round(raw)) > 1e-7:
            raise ValueError(f"Use passos de {spec['step_mv']} mV dentro dos limites do perfil.")
        return round(raw) & ((1<<spec['bits'])-1)
    if kind == 'vboot':
        raw = spec['anchor'] - number / spec['step']
        if not spec['low'] <= raw <= spec['high'] or abs(raw - round(raw)) > 1e-7:
            raise ValueError(f"Valor fora do intervalo do perfil ou dos passos de {spec['step']} V.")
        return round(raw)
    if kind == 'frequency':
        if not spec['min_khz'] <= number <= spec['max_khz']:
            raise ValueError(f"Frequência permitida: {spec['min_khz']} a {spec['max_khz']} kHz.")
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

def phase_rows(values):
    spec=current().get('phase_display') or {}
    rows=[];distribution=[];end=0
    for item in spec.get('loops',[]):
        count=_phases(item['id'],values)
        if count is None:
            return [(f"Fase {p['phase']}",'Aguardando leitura','—','—','Não lido') for p in _tables().get('phase_gain',[])]
        end+=count;distribution.append((end,item))
    for phase in _tables().get('phase_gain',[]):
        number=phase['phase'];gain=bits(values,phase['address'],phase['offset'],spec['gain_length'])
        loop=next((item for end,item in distribution if number<=end),None)
        texts=[]
        for key in ('fast','slow'):
            f=field(loop[key]) if loop else None
            code=bits(values,f['address'],f['offset'],f['length']) if f else None
            texts.append('—' if code is None else loop.get('slow_zero','0 A') if key=='slow' and code==0 else f"{code*loop['amps_per_code']} A")
        denominator=spec['balance_denominator']
        if gain is None:
            balance='Não lido'
        elif gain == 0:
            balance='0 · igual'
        else:
            factor=f'{denominator/(denominator-gain):.3f}'.replace('.', ',')
            balance=f'{gain} · fator {factor}'
        rows.append((f'Fase {number}',loop['label'] if loop else 'Fora da configuração',*texts,balance))
    return rows

def _phase_tables():
    return current()['tables']

class _LiveSeq:
    def __init__(self, key):
        self.key = key
    def _data(self):
        return tuple(_phase_tables().get(self.key) or [])
    def __iter__(self):
        return iter(self._data())
    def __getitem__(self, item):
        return self._data()[item]
    def __len__(self):
        return len(self._data())

class _LivePhaseBits(dict):
    def _data(self):
        return {item['symbol']: (item['address'], item['offset'], item['length'])
                for item in current()['fields'] if item['conversion']['type'] == 'phase_sum'}
    def __contains__(self, key):
        return key in self._data()
    def __getitem__(self, key):
        return self._data()[key]
    def __iter__(self):
        return iter(self._data())

LOOP1_PHASES = _LiveSeq('loop1_phases')
LOOP2_PHASES = _LiveSeq('loop2_phases')
RELATIVE_MV = _LiveSeq('relative_mv')
PHASE_BITS = _LivePhaseBits()
