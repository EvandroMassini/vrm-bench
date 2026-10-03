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

def compare(entry, actual):
    if actual is None:
        return "Não lido"
    if entry.mask == 0:
        return "Sem verificação"
    return "Confere" if ((actual ^ entry.value) & entry.mask) == 0 else "Diverge"

def region(profile, address):
    if profile == "IR35217":
        if 0x24 <= address <= 0x96:
            return "USER"
        if 0x98 <= address <= 0xA5:
            return "MFR"
        return "Fora da configuração USER/MFR"
    from .controller_store import region_name
    named = region_name(profile, address)
    if named is not None:
        return named
    return "Não documentada"

def read_plan(profile, entries):
    if profile != "IR35217":
        raise ValueError("IR3567B: a leitura do TXT usa PMBus com PEC na aba Arquivo TXT. Este lote por I²C direto permanece no IR35217.")
    return [e.address for e in entries if 0x24 <= e.address <= 0x96 or 0x98 <= e.address <= 0xA5]
