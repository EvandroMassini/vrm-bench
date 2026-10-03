"""Configuration parsing and comparison. No hardware dependencies."""
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Entry:
    address: int
    value: int
    mask: int

def parse_config(text):
    result, seen = [], set()
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3 or any(not re.fullmatch(r"[0-9a-fA-F]{2}", p) for p in parts):
            raise ValueError(f"Linha {number}: esperados três bytes hexadecimais.")
        address, value, mask = (int(p, 16) for p in parts)
        if address in seen:
            raise ValueError(f"Linha {number}: endereço duplicado {address:02X}.")
        seen.add(address)
        result.append(Entry(address, value, mask))
    if not result:
        raise ValueError("Arquivo vazio.")
    return result

def parse_dump_tolerant(text):
    """Keep every resolvable byte. Contradictory duplicates and broken lines are counted, not fatal to the file."""
    kept, rejected, issues = {}, set(), []
    for number, line in enumerate(text.splitlines(), 1):
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split()
        if len(parts) != 3 or any(not re.fullmatch(r"[0-9a-fA-F]{2}", part) for part in parts):
            issues.append(f"Linha {number}: formato inválido. Linha ignorada.")
            continue
        address, value, mask = (int(part, 16) for part in parts)
        if address in rejected:
            issues.append(f"Linha {number}: {address:02X} já estava contraditório. Linha ignorada.")
            continue
        previous = kept.get(address)
        if previous is None:
            kept[address] = Entry(address, value, mask)
            continue
        if previous.value != value:
            rejected.add(address)
            del kept[address]
            issues.append(f"{address:02X}: valores {previous.value:02X} e {value:02X}. Parâmetro ignorado.")
            continue
        issues.append(f"{address:02X}: endereço repetido. Mantido o primeiro valor.")
    if not kept and not issues:
        issues.append("Arquivo sem valores.")
    return list(kept.values()), issues

def compare(entry, actual):
    if actual is None:
        return "Não lido"
    if entry.mask == 0:
        return "Sem verificação"
    return "Confere" if ((actual ^ entry.value) & entry.mask) == 0 else "Diverge"

def region(profile, address):
    from .controller_store import region_name
    named = region_name(profile, address)
    if named is not None:
        return named
    return "Não documentada"

def read_plan(profile, entries):
    from .controller_store import get
    try:
        chip = get(profile)
    except KeyError:
        raise ValueError('Selecione o CI correto na lista Controlador antes de ler a placa.') from None
    spans = [(item['start'], item['end']) for item in chip.get('regions') or []]
    if not spans:
        raise ValueError('O JSON selecionado não declara regiões de leitura.')
    return [entry.address for entry in entries if any(start <= entry.address <= end for start, end in spans)]
