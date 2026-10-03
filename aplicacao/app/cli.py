"""CLI offline funcional sem dependências externas; hardware requer pyserial."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from .controller_store import select
from .core import parse_config, read_plan, compare
from .transport import Pico, Simulated

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--port", help="Omitir para simulação explícita")
    parser.add_argument("--address", type=lambda x: int(x,16), help="Endereço I2C direto, 7 bits HEX")
    parser.add_argument("--controller", required=True, help="Id do JSON em controllers")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    select(args.controller)
    if args.port and (args.address is None or not 8 <= args.address <= 0x77 or args.address == 0x0C):
        parser.error("--port exige --address válido de 7 bits")
    entries = parse_config(args.file.read_text(encoding="utf-8-sig"))
    source = "Pico USB" if args.port else "SIMULAÇÃO"
    print(source)
    link = Pico(args.port) if args.port else Simulated(entries)
    values = {}
    try:
        for address in read_plan(args.controller, entries):
            values[f"{address:02X}"] = link.read(args.address or 0x30, address)
    finally:
        link.close()
    for entry in entries:
        value = values.get(f"{entry.address:02X}")
        print(f"{entry.address:02X} {compare(entry,value)}")
    capture = dict(source=source, profile=args.controller, address_7bit=args.address,
                   timestamp_utc=datetime.now(timezone.utc).isoformat(), values=values)
    if args.output:
        args.output.write_text(json.dumps(capture, indent=2, ensure_ascii=False), encoding="utf-8")
if __name__ == "__main__":
    main()
