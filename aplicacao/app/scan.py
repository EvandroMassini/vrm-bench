from .transport import ADDRESSES

def scan_bus(link, cancelled, progress):
    """Return partial results even on cancellation/error; never retry bus faults."""
    result = dict(addresses=[], checked=0, complete=False, cancelled=False, error=None)
    for address in ADDRESSES:
        if cancelled.is_set():
            result["cancelled"] = True
            return result
        try:
            ack = link.probe(address)
        except Exception as exc:
            result["error"] = str(exc)
            return result
        result["checked"] += 1
        if ack:
            result["addresses"].append(address)
        progress(result["checked"], address, ack)
    result["complete"] = True
    return result
