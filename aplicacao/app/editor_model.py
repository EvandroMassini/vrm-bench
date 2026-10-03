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
    return str(address) not in current()['parameters']['write_masks']

_IMPASSABLE = frozenset(('mode_pair', 'phase_layout', 'match'))

def field_mask(field):
    offset, length = field.get('offset'), field.get('length')
    if not isinstance(offset, int) or not isinstance(length, int):
        return None
    if length < 1 or offset < 0 or offset + length > 8:
        return None
    return ((1 << length) - 1) << (8 - offset - length)

def field_code(field, value):
    mask = field_mask(field)
    if mask is None:
        return None
    return (value >> (8 - field['offset'] - field['length'])) & ((1 << field['length']) - 1)

def value_is_validated(field, code):
    spec = field.get('conversion') or {}
    if not spec.get('editable'):
        return False
    choices = [item.get('code') for item in field.get('choices') or [] if 'code' in item]
    return not choices or code in choices

def editable(f, values):
    if f['address'] not in values or _blocked(f['address']):
        return False
    mask=((1<<f['length'])-1)<<(8-f['offset']-f['length'])
    if mask & ~current()['parameters']['write_masks'].get(str(f['address']),0):return False
    return conv.editable(f['symbol'], values)

def lock_reason(f, values):
    """Why Novo valor stays closed. None when the field can be edited."""
    spec = f.get('conversion') or {}
    if not spec.get('editable'):
        kind = spec.get('type')
        if kind == 'mode_pair':
            bits = spec.get('bits') or []
            shown = ' e '.join(f'{int(item["address"]):02X}' for item in bits)
            return f'Esse nome junta os registradores {shown} e não tem um código único para gravar.'
        if kind == 'phase_layout':
            return f'Índice de fases no registrador {f["address"]:02X}. O programa não grava esse byte. Mudar o índice não cria fases na placa.'
        if kind == 'match':
            return 'Identificação lida do circuito. Não é um valor para gravar.'
        return 'A leitura está decodificada. A escrita deste campo está desligada no mapa do controlador.'
    if _blocked(f['address']):
        return f'O registrador {f["address"]:02X} não é gravado. O mapa deste CI bloqueia esse byte.'
    if f['address'] not in values:
        return 'Leia os valores atuais para editar este campo.'
    if conv.editable(f['symbol'], values):
        return None
    gate = (current().get('tables') or {}).get('phase_count') or {}
    gate_text = f'{int(gate["address"]):02X}' if 'address' in gate else f'{f["address"]:02X}'
    if spec.get('type') == 'phase_current':
        if 'address' not in gate:
            return 'A edição depende da configuração de fases declarada no JSON deste CI.'
        code = conv.bits(values, gate['address'], gate['offset'], gate['length'])
        if code is None:
            return f'A edição depende da configuração das saídas, no registrador {gate_text}.'
        key = 'loop1_phases' if 'LOOP_1' in f['symbol'] else 'loop2_phases'
        if current()['tables'][key][code] == 0:
            return 'Este loop não tem fases na configuração lida. Qualquer código positivo continua valendo 0 A.'
        return f'A edição depende da configuração das saídas, no registrador {gate_text}.'
    if spec.get('type') in ('vid_offset', 'vboot'):
        return f'Edição disponível quando a personalidade exigida pelo mapa está ativa no registrador {gate_text}.'
    return 'Escrita indisponível para o valor lido.'

def numeric(f, values):
    return conv.numeric(f['symbol'], code(f, values), values)

def display(f, values):
    if f['address'] not in values:
        return 'Não lido'
    text = conv.display(f['symbol'], code(f, values), values)
    return text if text is not None else 'Conversão não validada'

def import_caption(field, code, values):
    for choice in field.get('choices') or []:
        if choice.get('code') == code and choice.get('text'):
            return choice['text']
    text = conv.display(field['symbol'], code, values)
    if text and text not in ('Conversão não validada', 'Não lido'):
        return text
    return str(code)

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
        if item.get('edit_priority',1)==0:
            return (0, 0)
        index = conv.phase_index(symbol)
        return (1, index or 0) if index else (2, 0)

    for item in sorted(FIELDS, key=rank):
        raw = edits.get(item['symbol'], '')
        if raw is None or raw == '' or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            if isinstance(raw, int):
                if field_mask(item) is None or (item.get('conversion') or {}).get('type') in _IMPASSABLE:
                    raise ValueError('Este parâmetro não tem um código único para gravar.')
                coded = raw
                if not 0 <= coded < (1 << item['length']):
                    raise ValueError('Valor fora da faixa representável do parâmetro.')
            else:
                coded = encode(item, raw, target)
        except ValueError as exc:
            raise ValueError(label(item) + ': ' + str(exc)) from exc
        if item['address'] not in target:
            continue
        shift = 8 - item['offset'] - item['length']
        mask = ((1 << item['length']) - 1) << shift
        old = target[item['address']]
        target[item['address']] = (old & ~mask) | (coded << shift)
        if code(item, values) != coded:
            rows.append(dict(name=label(item), group=group(item), before=display(item, values), after=display(item, target)))
    changes = {address: value for address, value in target.items() if value != values[address]}
    return changes, rows

def prepare_import(entries, live_values, compare_mask):
    """Map dump bytes onto JSON fields. Only an impossible code is left out."""
    by_address = {}
    for field in FIELDS:
        by_address.setdefault(field['address'], []).append(field)
    issues = []
    ignored = []
    unvalidated = []
    imported = {}
    proposals = {}
    guards = set(current()['parameters'].get('import_guard_registers') or [])
    guard_differs = False
    for entry in entries:
        fields = by_address.get(entry.address)
        if not fields:
            continue
        expected = compare_mask(entry.address)
        if entry.mask != expected:
            issues.append(f"{entry.address:02X}: máscara {entry.mask:02X} do arquivo, {expected:02X} no JSON. Valor mantido.")
        conflict = entry.mask != expected
        if live_values and entry.address in guards and entry.value != live_values.get(entry.address):
            guard_differs = True
            conflict = True
        imported[entry.address] = entry.value
        for field in fields:
            code = field_code(field, entry.value)
            kind = (field.get('conversion') or {}).get('type')
            if code is None or kind in _IMPASSABLE:
                ignored.append(field['symbol'])
                continue
            proposals[field['symbol']] = code
            same = bool(live_values) and entry.address in live_values and field_code(field, live_values[entry.address]) == code
            if same:
                continue
            if conflict or not value_is_validated(field, code):
                unvalidated.append(field['symbol'])
    if guard_differs:
        issues.append("Modo do dump difere da placa. Os parâmetros correspondentes foram mantidos.")
    return dict(imported=imported, proposals=proposals, issues=issues, ignored=ignored, unvalidated=unvalidated)
