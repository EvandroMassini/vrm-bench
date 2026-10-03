"""Community register references loaded from the controller JSON."""
from .controller_store import current
_catalog=current()['catalog']
SOURCE=_catalog['source']
LABELS={int(key):value for key,value in _catalog['labels'].items()}
INITIAL=_catalog['initial']
EXTENDED=' '.join(f'{r:02X}' for r in LABELS)

def metadata(registers):
    return dict(source=SOURCE,authority='Implementação comunitária; não é mapa oficial integral',
                interpretation='Valores brutos. Funções indicadas pela referência; não validadas fisicamente nesta placa.',
                registers=[dict(register_hex=f'{r:02X}',description=LABELS.get(r,'Fora do catálogo comunitário selecionado')) for r in registers])
