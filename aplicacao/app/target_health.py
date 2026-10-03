"""Live controller check, distinct from USB connection to the Pico."""
def verify_target(link,address,profile):
    from .bus_health import check
    from .controller_store import get
    try:
        check(link,{})
        try:
            chip=get(profile)
        except KeyError:
            raise ValueError('Verificação deste controlador ainda não disponível.')
        identity=chip['identity']
        response=link.pm_read(address,identity['model_command'],True,False)
        if response.get('raw_hex')!=identity['model_hex'] or response.get('pec_verified') is not True:
            raise ValueError('Identificação ou integridade da resposta não confere.')
    except Exception as exc:
        raise ValueError('Não foi possível confirmar resposta do CI. Verifique alimentação da placa, GND comum e SDA/SCL. '
                         'A conexão USB do Pico não confirma a comunicação com a placa. Detalhe: '+str(exc)) from exc
