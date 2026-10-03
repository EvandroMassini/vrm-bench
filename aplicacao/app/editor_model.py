"""Human-unit edits. Field definitions come from the selected controller JSON."""
from . import conversions as conv
from .controller_store import current

class _LiveFields:
    def __iter__(self):
        return iter(current()['fields'])

    def __len__(self):
        return len(current()['fields'])

FIELDS = _LiveFields()

def label(f):
    return f.get('label') or f['symbol']

def group(f):
    return f.get('group') or 'Compartilhados'

def code(f, values):
    return (values[f['address']] >> (8 - f['offset'] - f['length'])) & ((1 << f['length']) - 1)

def unit(f):
    return f.get('unit') or ''

def hint(f):
    return f.get('hint') or unit(f) or 'Conversão pendente'

def _blocked(address):
    return address in set(current().get('parameters', {}).get('blocked') or [])

def editable(f, values):
    if f['address'] not in values or _blocked(f['address']):
        return False
    return conv.editable(f['symbol'], values)

def lock_reason(f, values):
    """Why Novo valor stays closed. None when the field can be edited."""
    spec = f.get('conversion') or {}
    if not spec.get('editable'):
        kind = spec.get('type')
        if kind == 'mode_pair':
            return 'O texto junta a personalidade do registrador 14 com o modo de aplicação do registrador 61. Esse nome não tem um código único, e o registrador 14 não entra na gravação.'
        if kind == 'phase_layout':
            return 'Índice de fases dentro do registrador 14. Esse byte também guarda a personalidade e a sequência, e o programa não o grava. Mudar o índice não cria fases na placa.'
        if kind == 'match':
            return 'Identificação lida do circuito. Não é um valor para gravar.'
        return 'A leitura está decodificada. A escrita deste campo está desligada no mapa do controlador.'
    if _blocked(f['address']):
        return 'O registrador 14 não é gravado. O mesmo byte guarda a sequência de partida, a personalidade e a configuração das fases.'
    if f['address'] not in values:
        return 'Leia os valores atuais para editar este campo.'
    if conv.editable(f['symbol'], values):
        return None
    if spec.get('type') == 'phase_current':
        where = current()['tables']['phase_count']
        code = conv.bits(values, where['address'], where['offset'], where['length'])
        if code is None:
            return 'A edição depende da configuração das saídas, no registrador 14.'
        key = 'loop1_phases' if 'LOOP_1' in f['symbol'] else 'loop2_phases'
        if current()['tables'][key][code] == 0:
            return 'Este loop não tem fases na configuração lida. Qualquer código positivo continua valendo 0 A.'
        return 'A edição depende da configuração das saídas, no registrador 14.'
    if spec.get('type') in ('vid_offset', 'vboot'):
        return 'Edição disponível quando a personalidade AMD está ativa no registrador 14.'
    return 'Escrita indisponível para o valor lido.'

def numeric(f, values):
    return conv.numeric(f['symbol'], code(f, values), values)

def display(f, values):
    if f['address'] not in values:
        return 'Não lido'
    text = conv.display(f['symbol'], code(f, values), values)
    return text if text is not None else 'Conversão não validada'

def proposal_text(f, values):
    if not editable(f, values):
        return None
    if f['conversion']['type'] == 'enum':
        return display(f, values)
    if f['conversion'].get('zero') and code(f, values) == 0:
        return f['conversion']['zero']
    number = numeric(f, values)
    if number is None:
        return None
    return f'{number:.6f}'.rstrip('0').rstrip('.')

def encode(f, text, values):
    if not editable(f, values):
        raise ValueError('Conversão de escrita não validada para este parâmetro.')
    coded = conv.encode(f['symbol'], text, values)
    if not 0 <= coded < (1 << f['length']):
        raise ValueError('Valor fora da faixa representável do parâmetro.')
    return coded

def plan(values, edits):
    """Blank inputs are absent; dependent thermal fields use the proposed TEMP_MAX."""
    target = dict(values)
    rows = []

    def rank(item):
        symbol = item['symbol']
        if symbol == 'TEMP_MAX':
            return (0, 0)
        index = conv.phase_index(symbol)
        return (1, index or 0) if index else (2, 0)

    for item in sorted(FIELDS, key=rank):
        raw = edits.get(item['symbol'], '')
        if raw is None or raw == '' or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            if isinstance(raw, int):
                if not editable(item, target):
                    raise ValueError('Conversão de escrita não validada para este parâmetro.')
                coded = raw
                if not 0 <= coded < (1 << item['length']):
                    raise ValueError('Valor fora da faixa representável do parâmetro.')
            else:
                coded = encode(item, raw, target)
        except ValueError as exc:
            raise ValueError(label(item) + ': ' + str(exc)) from exc
        shift = 8 - item['offset'] - item['length']
        mask = ((1 << item['length']) - 1) << shift
        old = target[item['address']]
        target[item['address']] = (old & ~mask) | (coded << shift)
        if code(item, values) != coded:
            rows.append(dict(name=label(item), group=group(item), before=display(item, values), after=display(item, target)))
    changes = {address: value for address, value in target.items() if value != values[address]}
    return changes, rows
