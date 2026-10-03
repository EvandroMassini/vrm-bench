def explanation(error):
    if any(code in str(error) for code in ('BUS_BUSY','BUS_CONFLICT','SCL_TIMEOUT','BUS_NOT_IDLE')):
        return ('Barramento indisponível. Verifique se a placa está alimentada, o GND comum e as conexões SDA/SCL. '
                'Uma linha baixa ou atividade também pode causar este erro; o Pico não mede a alimentação da placa. '
                'Use Diagnóstico / busca → Observar SDA/SCL. Não houve confirmação de placa desligada.')
    return ''

def check(link,result):
    observation=link.observe()
    result['bus_observation']=observation
    if observation['sda_low_samples'] or observation['scl_low_samples'] or observation['changes']:
        raise ValueError('BUS_NOT_IDLE: SDA/SCL não permaneceram altas durante a observação. '+explanation('BUS_NOT_IDLE'))

