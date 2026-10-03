"""Copy a dump's USER image into the selected controller.

Trim and MFR stay on the destination chip. The range and the unlock bytes
come from the controller JSON. IR3567B unlock follows ProgramComanche:
registers 228 and 229 are written as 00 before the USER block.
"""
from .controller_store import current
from .transactions import execute


def span(profile=None):
    verify = (profile or current())['verify']
    start, end = int(verify['user_start']), int(verify['user_end'])
    if start > end:
        raise ValueError('Faixa USER inválida no JSON')
    return start, end


def unlock_steps(profile=None):
    items = ((profile or current()).get('restore') or {}).get('unlock') or []
    steps = []
    for item in items:
        register, value = item.get('register'), item.get('value')
        if type(register) is not int or type(value) is not int or not 0 <= register <= 255 or not 0 <= value <= 255:
            raise ValueError('Desbloqueio inválido no JSON')
        steps.append((register, value))
    return steps


def image_from_entries(entries, profile=None):
    start, end = span(profile)
    found = {}
    for entry in entries:
        if start <= entry.address <= end:
            found[entry.address] = entry.value
    missing = [address for address in range(start, end + 1) if address not in found]
    if missing:
        shown = ', '.join(f'{address:02X}' for address in missing[:12])
        if len(missing) > 12:
            shown += f' e mais {len(missing) - 12}'
        raise ValueError('O arquivo não tem a área USER completa. Faltam: ' + shown + '.')
    return found


def prepare(entries, live, profile=None):
    """Plan the copy. problems blocks any write and any slot."""
    profile = profile or current()
    start, end = span(profile)
    image = image_from_entries(entries, profile)
    problems = []
    if any(address not in live for address in image):
        problems.append('A leitura deste CI não cobre a área USER. Leia a placa de novo.')
    projected = dict(live)
    projected.update(image)
    for guard in profile['protocol'].get('guards') or []:
        _expect(problems, projected, guard['register'], guard['mask'], guard['value'], 'A imagem não atende a condição do perfil')
    for step in profile['recipes'].get('commit') or []:
        if step.get('op') != 'assert':
            continue
        _expect(problems, projected, step['register'], step['mask'], step['value'], 'A gravação do slot exige outro estado')
    writes = [address for address in range(start, end + 1) if address in live and live[address] != image[address]]
    return dict(image=image, writes=writes, problems=problems, unlock=unlock_steps(profile), start=start, end=end)


def _expect(problems, values, register, mask, value, prefix):
    if register not in values:
        problems.append(f'{prefix}: registrador {register:02X} ausente.')
        return
    if (values[register] & mask) != value:
        problems.append(f'{prefix}: {register:02X} está {values[register]:02X}, a receita exige {(values[register] & ~mask) | value:02X} nessa máscara.')


def write_byte(link, address, expected, target):
    """Persistent byte write. Identity is still checked; board-mode guards are not."""
    result = execute(link, [
        dict(op='assert', register=address, mask=255, value=expected),
        dict(op='persistent', register=address, mask=255, value=target),
    ])
    if not result.get('complete'):
        raise ValueError(result.get('error') or f'{address:02X} não confirmado')
    return result


def program(link, plan):
    """Unlock, then write differing USER bytes. Does not consume a slot."""
    report = dict(ok=False, written=[], error=None)
    direct = int(current()['bus']['direct'], 16)
    try:
        for register, value in plan['unlock']:
            seen = link.register_read(direct, register)
            if not seen.get('pec_verified'):
                raise ValueError(f'Leitura de {register:02X} sem integridade')
            if seen['value'] == value:
                continue
            write_byte(link, register, seen['value'], value)
            report['written'].append(register)
        for address in plan['writes']:
            write_byte(link, address, plan['live'][address], plan['image'][address])
            report['written'].append(address)
        report['ok'] = True
    except Exception as exc:
        report['error'] = str(exc)
    return report


def summary(plan, chip_id):
    lines = [
        f'CI selecionado: {chip_id}.',
        f'Área USER {plan["start"]:02X}–{plan["end"]:02X}: {plan["end"] - plan["start"] + 1} bytes do arquivo.',
        f'{len(plan["writes"])} byte(s) diferem da RAM deste CI e serão copiados.',
        'O trim e a área de fabricante deste CI permanecem os dele.',
        'Depois a imagem USER é gravada em 1 slot. As saídas são interrompidas durante essa gravação.',
        'Continuar?',
    ]
    return '\n'.join(lines)
