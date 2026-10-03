"""Read-only engineering text. Coefficients come from the controller JSON."""
from .controller_store import field
from .conversions import report_text

def _register(values, address):
    item = values.get(f'{address:02X}')
    if isinstance(item, dict) and isinstance(item.get('value'), int):
        return item['value']
    if isinstance(item, int):
        return item
    return None

def convert(symbol, code, values):
    if code is None:
        return 'Não lido', ''
    try:
        item = field(symbol)
    except KeyError:
        return 'Código bruto; conversão não confirmada', ''
    spec = item['conversion']
    kind = spec['type']
    source = item.get('source', '')
    if kind == 'frequency':
        if code == 0:
            return 'Indefinido (período zero)', source
        return f'{1e6 / (code * spec["period_us"]):.2f} kHz (configuração)', source
    if kind == 'temperature':
        return f'{code + spec["base"]} °C (limite VR_HOT)', source
    if kind == 'temperature_plus':
        other = _register(values, spec['from']['address'])
        if other is None:
            return 'Depende de TEMP_MAX (registro 32 ausente)', source
        temp = (other >> spec['from']['shift']) & spec['from']['mask']
        return f'{code + temp + spec["add"]} °C (limite térmico OTP)', source
    if kind == 'vid_offset':
        signed = code if code < 8 else code - 16
        if signed == -1:
            return '0 mV (offset codificado; não é VOUT)', '(código com sinal + 1) × passo'
        mode = _register(values, spec['require']['address'])
        if mode is not None and mode & spec['require']['mask']:
            return f'{(signed + 1) * spec["step_mv"]:g} mV (offset configurado)', source
        return 'Passo depende do modo e VR125_MODE_NVM; sem conversão', ''
    traced = report_text(symbol, code, values)
    if traced:
        return traced
    return 'Código bruto; conversão não confirmada', ''
