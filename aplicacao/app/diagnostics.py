from datetime import datetime, timezone
from .transport import ADDRESSES, COMMANDS, TargetRejected

def addresses_from_text(text):
    result=[]
    for token in text.replace(',',' ').split():
        address=int(token,16)
        if address not in ADDRESSES:raise ValueError(f"Endereço reservado/inválido: {token}")
        if address not in result:result.append(address)
    if not result:raise ValueError("Informe ao menos um endereço de 7 bits em HEX.")
    return result

def diagnose(link, addresses, commands, khz, pec, split, cancelled, progress):
    """Bounded user-selected command list; retain partial results and stop on bus faults."""
    if not addresses or any(a not in ADDRESSES for a in addresses):raise ValueError("Endereços inválidos")
    if not commands or any(c not in COMMANDS for c in commands):raise ValueError("Comandos inválidos")
    if pec and split:raise ValueError("PEC não disponível com STOP intermediário")
    report=dict(kind="diagnostics",timestamp_utc=datetime.now(timezone.utc).isoformat(),
                addresses=addresses,commands=commands,khz_nominal=khz,pec=pec,
                framing="STOP + START experimental" if split else "repeated START",
                results=[],complete=False,cancelled=False,error=None)
    try:
        link.set_speed(khz)
        for address in addresses:
            for command in commands:
                if cancelled.is_set():
                    report['cancelled']=True
                    return report
                row=dict(address_7bit=address,command_hex=f"{command:02X}",
                         timestamp_utc=datetime.now(timezone.utc).isoformat())
                try:
                    row.update(status="response",response=link.pm_read(address,command,pec,split))
                except TargetRejected as exc:
                    row.update(status="rejected",error=str(exc))
                except Exception as exc:
                    row.update(status="fatal",error=str(exc))
                    report['results'].append(row)
                    progress(row)
                    raise
                report['results'].append(row)
                progress(row)
        report['complete']=True
    except Exception as exc:
        report['error']=str(exc)
    return report
