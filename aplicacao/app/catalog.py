"""Community register references loaded from the selected controller JSON."""
from .controller_store import current

def _catalog():
    return current().get('catalog') or {}

def _label_address(key):
    base = _catalog().get('address_base') or 'decimal'
    return int(str(key), 16 if base == 'hex' else 10)

class _LiveLabels(dict):
    def _data(self):
        return {_label_address(key): value for key, value in (_catalog().get('labels') or {}).items()}
    def get(self, key, default=None):
        return self._data().get(key, default)
    def __iter__(self):
        return iter(self._data())
    def __len__(self):
        return len(self._data())
    def items(self):
        return self._data().items()
    def __contains__(self, key):
        return key in self._data()

class _LiveText:
    def __init__(self, loader):
        self._loader = loader
    def _text(self):
        return str(self._loader() or '')
    def __str__(self):
        return self._text()
    def split(self, *args, **kwargs):
        return self._text().split(*args, **kwargs)

def _extended():
    return ' '.join(f'{address:02X}' for address in _LiveLabels()._data())

LABELS = _LiveLabels()
INITIAL = _LiveText(lambda: _catalog().get('initial'))
EXTENDED = _LiveText(_extended)
SOURCE = _LiveText(lambda: _catalog().get('source'))

def metadata(registers):
    catalog = _catalog()
    labels = LABELS._data()
    return dict(source=str(SOURCE), authority=catalog.get('authority') or 'Mapa do JSON selecionado.',
                interpretation=catalog.get('interpretation') or 'Valores brutos do CI selecionado.',
                registers=[dict(register_hex=f'{register:02X}', description=labels.get(register, 'Fora do catálogo do CI selecionado')) for register in registers])
