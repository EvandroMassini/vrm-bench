"""Read-only, bounded telemetry. No PAGE, fault clearing, or configuration writes."""
import re
from datetime import datetime,timezone
from .transport import crc8,TargetRejected,ADDRESSES
from .controller_store import current

def _commands():
    return {item['code']: (item['name'], item['bytes'], item['unit']) for item in current()['telemetry']['commands']}

class _LiveCommands(dict):
    def __getitem__(self, key):
        return _commands()[key]

    def __contains__(self, key):
        return key in _commands()

    def __iter__(self):
        return iter(_commands())

FIELDS = _LiveCommands()

def signed(value,bits):
    return value-(1<<bits) if value&(1<<(bits-1)) else value

def linear11(word):
    return signed(word&0x7FF,11)*2.0**signed(word>>11,5)

def decode_fixed(response,address,command):
    length=FIELDS[command][1]
    m=re.fullmatch(r'OK BLOCK ([0-9A-F]{2}) ([0-9A-F]+) ([0-9A-F]{2})',response)
    if not m or int(m[1],16)!=length or len(m[2])!=2*length:
        raise ValueError('Resposta de telemetria malformada; coleta interrompida')
    data=bytes.fromhex(m[2])
    expected=crc8(bytes([address<<1,command,address<<1|1])+data)
    received=int(m[3],16)
    if received!=expected:
        raise ValueError(f'PEC inválido em {command:02X}: recebido {received:02X}, esperado {expected:02X}')
    return dict(raw_hex=m[2],value_raw=int.from_bytes(data,'little'),pec_verified=True,
                pec_received=f'{received:02X}',pec_expected=f'{expected:02X}')

def output_offset_nibble(config,offset):
    """Loop nibble of the VID offset register when only one AMD loop is present."""
    vout=current()['telemetry']['vout']
    tables=current()['tables']
    if not config&vout['amd_mask']:return None
    index=config&31
    first,second=tables['loop1_phases'][index],tables['loop2_phases'][index]
    if bool(first)==bool(second):return None
    return (offset>>4) if first else (offset&15)

def vout_pin(linear,nibble):
    """Linear16 plus the gap stored for this controller."""
    if linear is None or nibble is None:return linear
    vout=current()['telemetry']['vout']
    return linear+(vout['zero_volts'] if nibble==vout['zero_nibble'] else vout['other_volts'])

def interpret(command,result,vout_mode,offset_nibble=None):
    word=result['value_raw']
    if FIELDS[command][2]=='hex':return dict(display=f'0x{word:0{FIELDS[command][1]*2}X}',unit='',value=None)
    if command==0x8B:
        if vout_mode is None or vout_mode>>5!=0:
            return dict(display='RAW — VOUT_MODE ausente/não Linear',unit='',value=None)
        value=vout_pin(word*2.0**signed(vout_mode&31,5),offset_nibble)
        fmt='Linear16 mais 56,25 mV no ajuste 0; nos demais, mais 50 mV' if offset_nibble is not None else 'Linear16; expoente lido em VOUT_MODE'
    else:
        value=linear11(word)
        fmt='Linear11; referência de família, escala ainda não validada na placa'
    return dict(display=f'{value:.6g} {FIELDS[command][2]}',unit=FIELDS[command][2],value=value,format=fmt)

def collect(link,address,khz,cycles,cancelled,progress,interval=1.0):
    if link.version<5:raise ValueError('Atualize o Pico para protocolo v5')
    if address not in ADDRESSES or cycles not in (1,10):raise ValueError('Parâmetros inválidos')
    report=dict(kind='telemetry',address_7bit=address,khz_nominal=khz,pec=True,
                timestamp_utc=datetime.now(timezone.utc).isoformat(),samples=[],complete=False,
                cancelled=False,error=None,loop='Saída atualmente endereçada; PAGE não alterada',
                interpretation='Referência IR3565B/família; confirmar escala com medição externa')
    unsupported=set()
    try:
        link.set_speed(khz)
        chip=current();identity=chip['identity'];vout=chip['telemetry']['vout']
        model=link.pm_read(address,identity['model_command'],True,False)
        report['model_read']=model
        if model['raw_hex']!=identity['model_hex'] or not model['pec_verified']:
            raise ValueError(f"Modelo diferente de {identity['model_hex']}h ou sem PEC válido; coleta não iniciada")
        report['identity']=identity['label']
        nibble=None
        try:
            config=link.register_read(address,vout['config_register']);offset=link.register_read(address,vout['offset_register'])
            if config.get('pec_verified') and offset.get('pec_verified'):
                nibble=output_offset_nibble(config['value'],offset['value'])
                report['output_adjust_hex']=f"{offset['value']:02X}"
        except Exception:
            nibble=None
        for index in range(cycles):
            if cancelled.is_set():report['cancelled']=True;return report
            sample=dict(index=index+1,timestamp_utc=datetime.now(timezone.utc).isoformat(),readings=[])
            report['samples'].append(sample)
            mode=None
            # Read CML first and again last: unsupported requests can latch communication faults.
            for command in [0x7E]+[c for c in FIELDS if c!=0xD6]+[0x7E]:
                if cancelled.is_set():report['cancelled']=True;return report
                if command in unsupported:continue
                row=dict(command_hex=f'{command:02X}',name=FIELDS[command][0],sample=index+1,
                         timestamp_utc=datetime.now(timezone.utc).isoformat())
                try:
                    data=link.telemetry_read(address,command)
                    if command==0x20:mode=data['value_raw']
                    row.update(status='response',**data,**interpret(command,data,mode,nibble if command==0x8B else None))
                except TargetRejected as exc:
                    row.update(status='unsupported',error=str(exc),display=str(exc))
                    if str(exc)!='ERR PMBUS_COMMAND':
                        row['status']='fatal'
                        sample['readings'].append(row);progress(row)
                        raise
                    unsupported.add(command)
                except Exception as exc:
                    row.update(status='fatal',error=str(exc),display=str(exc))
                    sample['readings'].append(row);progress(row)
                    raise
                sample['readings'].append(row);progress(row)
            if index+1<cycles and cancelled.wait(interval):
                report['cancelled']=True;return report
        report['complete']=True
    except Exception as exc:
        report['error']=str(exc)
    return report
