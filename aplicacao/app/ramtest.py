import re
from datetime import datetime,timezone
from .bus_health import check,explanation
from .registers import map_interface

def decode(response):
    m=re.fullmatch(r'OK RAMTEST ([01][0-9A-F]) ([01][0-9A-F]) ([0-9A-F]{2}) ([01][0-9A-F]) ([01][0-9A-F]) ([0-9A-F]{2}) ([0-9A-F]{2})',response)
    if not m:raise ValueError('Resposta RAMTEST inválida; restauração não confirmada.')
    write,read,value,restore,final,last,mode=[int(x,16) for x in m.groups()]
    if any(x not in (0,1) for x in (write,read,restore,final)):raise ValueError('Flags RAMTEST inválidos; restauração não confirmada.')
    return dict(write_ack=bool(write),changed_read_ok=bool(read),changed_hex=f'{value:02X}',
        restore_ack=bool(restore),final_read_ok=bool(final),final_hex=f'{last:02X}',mode_hex=f'{mode:02X}',
        change_confirmed=bool(write and read and value==0xEF),restoration_confirmed=bool(final and last==0xFF))

def experiment(link,before_send=None,hold=False):
    if hold and link.version not in (10,11,12):raise ValueError('O ensaio de 10 segundos exige firmware 0.17, protocolo 10.')
    if link.version not in (9,10,11,12):raise ValueError('O teste exige firmware v0.13, protocolo 9 RAMTEST.')
    result=dict(kind='ram_write_experiment',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        complete=False,error=None,command_sent=False,write_attempted=False,restoration_required=False,restoration_confirmed=None,
        hold_requested_ms=10000 if hold else 0,
        register_hex='26',original_hex='FF',test_hex='EF',pmbus_address_7bit=0x70,direct_i2c_address_7bit=8,
        scope='Ensaio limitado de offset loop 1. Sem comandos MTP. Efeito físico de tensão não medido pelo teste.')
    try:
        check(link,result)
        result['mapping']=mapping=map_interface(link,0x70,100)
        if not mapping['direct_i2c_enabled'] or mapping['direct_i2c_address_7bit']!=8:raise ValueError('D6 incompatível com o alvo fixo 08.')
        result['cml_before']=cml=link.telemetry_read(0x70,0x7E)
        if cml['value_raw']!=0:raise ValueError('STATUS_CML não está zerado; teste não iniciado.')
        result['baseline']=baseline=link.register_read(0x70,0x26)
        if baseline['value']!=0xFF or not baseline['pec_verified']:raise ValueError('26 deve ser FF com PEC; nenhuma escrita realizada.')
        if before_send is not None:before_send(result)
        result['command_sent']=True
        result['write_attempted']=None
        result['restoration_required']=None
        result.update(decode(link.request('RAMHOLD 08 26 FF EF 10000 RESTORE' if hold else 'RAMTEST 08 26 FF EF RESTORE')))
        result['hold_completed']=bool(hold and result['change_confirmed'])
        result['write_attempted']=True
        result['restoration_required']=True
        if not result['restoration_confirmed']:raise ValueError('Restauração NÃO confirmada. Desligue a alimentação da placa e não repita o teste.')
        result['after']=after=link.register_read(0x70,0x26)
        if after['value']!=0xFF or not after['pec_verified']:
            result['restoration_confirmed']=False
            raise ValueError('Verificação PMBus da restauração falhou. Desligue a placa.')
        result['cml_after']=link.telemetry_read(0x70,0x7E)
        result['complete']=True
    except Exception as exc:
        result['error']=str(exc)
        result['guidance']=explanation(exc)
        prewrite = re.fullmatch(r'ERR (BUS_BUSY|RAMTEST_MODEL|RAMTEST_MODE_READ|RAMTEST_BASELINE|RAMTEST_MODE_VALUE ([0-9A-F]{2}))', str(exc))
        detail=re.fullmatch(r'ERR RAMTEST_PRECHECK ([0-9A-F]{2}) (IDLE_BEFORE|POINTER|READ|STOP) (-?\d+)',str(exc))
        if result['command_sent'] and detail:
            result['write_attempted']=False
            result['restoration_required']=False
            result['precheck_failure']=dict(register_hex=detail[1],stage=detail[2],sdk_code=int(detail[3]))
            stages={'IDLE_BEFORE':'espera pelo barramento livre','POINTER':'envio do endereço do registro','READ':'recepção do byte','STOP':'conclusão do STOP e liberação do barramento'}
            result['guidance']=f'Teste interrompido antes da escrita. Restauração não necessária. Registro {detail[1]}: falha em {stages[detail[2]]}, código {detail[3]}.'
        elif result['command_sent'] and prewrite:
            result['write_attempted']=False
            result['restoration_required']=False
            if prewrite.group(2):result['mode_hex']=prewrite.group(2)
            result['guidance']='Teste interrompido antes da escrita. Nenhum valor de configuração foi alterado; restauração não necessária.'
            if str(exc)=='ERR RAMTEST_MODE_READ':result['guidance']+=' Falhou a leitura direta do registro 14.'
            elif prewrite.group(2):result['guidance']+=f' Registro 14={prewrite.group(2)}; bit 0x20 não está ativo.'
        elif result['command_sent'] and result['restoration_confirmed'] is None:
            result['guidance']+=' Estado da restauração desconhecido. Desligue a placa; não repita automaticamente.'
    return result
