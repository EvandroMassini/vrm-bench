"""USB protocol v1/v2. Discovery never probes unrelated serial devices."""

import re

import time

from datetime import datetime, timezone



def crc8(data):

    crc = 0

    for byte in data:

        crc ^= byte

        for _ in range(8):

            crc = ((crc << 1) ^ (7 if crc & 128 else 0)) & 255

    return crc



class TargetRejected(RuntimeError):

    """A completed target transaction failed; USB framing remains synchronized."""



COMMANDS = {0x98:"PMBUS_REVISION", 0x99:"MFR_ID", 0x9A:"MFR_MODEL", 0x9B:"MFR_REVISION"}

RECOVERABLE = {"ERR PMBUS_ADDR_W", "ERR PMBUS_ADDR_R", "ERR PMBUS_COMMAND", "ERR PMBUS_COUNT"}



def decode_mfr(response, address, pec, command=0x99):

    match = re.fullmatch(r"OK BLOCK ([0-9A-F]{2}) ([0-9A-F]+) ([0-9A-F]{2}|--)", response)

    if not match:

        raise ValueError("Resposta PMBus malformada.")

    count, raw, check = match.groups()

    if not 1 <= int(count, 16) <= 32 or len(raw) != int(count, 16) * 2:

        raise ValueError("Comprimento PMBus inválido.")

    data = bytes.fromhex(raw)

    if command == 0x98 and len(data) != 1:

        raise ValueError("PMBUS_REVISION exige um byte.")

    if pec:

        header = [address << 1, command, address << 1 | 1]

        if command != 0x98: header.append(len(data))

        expected = crc8(bytes(header) + data)

        if check == "--" or int(check, 16) != expected:

            raise ValueError("PEC inválido; resposta não validada.")

    elif check != "--":

        raise ValueError("PEC inesperado.")

    return dict(command=f"{COMMANDS[command]} (0x{command:02X})", raw_hex=raw,

                text="".join(chr(b) if 32 <= b <= 126 else "." for b in data),

                pec_verified=bool(pec), identification="Resposta de fabricante; modelo não confirmado")



ADDRESSES = tuple(a for a in range(0x08, 0x78) if a != 0x0C)



def serial_ports():

    from serial.tools import list_ports

    return [dict(device=p.device, description=p.description or "",

                 vid=p.vid, pid=p.pid, serial=p.serial_number or "")

            for p in sorted(list_ports.comports(), key=lambda p:p.device)]



def port_caption(port):
    device=port['device']
    description=(port.get('description') or '').strip()
    lowered=description.lower()
    if not description or description.upper()==device.upper() or any(word in lowered for word in ('pico','raspberry','rp2040')):
        description=f'Dispositivo Serial USB ({device})'
    return f'{device} — {description}'



def candidate(port):

    return port.get("vid") == 0x2E8A



def identify(ports, factory=None):

    factory = factory or Pico

    found, failures = [], []

    for p in ports:

        if not candidate(p):

            continue

        link = None

        try:

            link = factory(p["device"])

            found.append(dict(p, version=link.version))

        except Exception as exc:

            failures.append(f'{p["device"]}: {exc}')

        finally:

            if link is not None:

                link.close()

    return found, failures



class Pico:

    def __init__(self, port):

        import serial

        self.serial = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=1)

        self.serial.dtr = True  # Arduino-Pico USB CDC requires an open DTR session.

        self.serial.rts = False

        self.serial.port = port

        self.trace = []

        try:

            self.serial.open()

            time.sleep(0.25)

            self.serial.reset_input_buffer()

            hello = self.request("HELLO")

            if hello not in tuple(f"OK INFINEON-PICO {v} READONLY" for v in (1,2,3,4,5,6))+("OK INFINEON-PICO 7 RAMTEST","OK INFINEON-PICO 8 RAMTEST","OK INFINEON-PICO 9 RAMTEST","OK INFINEON-PICO 10 RAMTEST","OK INFINEON-PICO 11 RAMTEST","OK INFINEON-PICO 12 RAMTEST","OK INFINEON-PICO 13 RAMTEST","OK INFINEON-PICO 14 RAMTEST","OK INFINEON-PICO 15 RAMTEST"):

                raise RuntimeError("Firmware não reconhecido.")

            self.version = int(hello.split()[2])

        except Exception:

            self.close()

            raise



    def request(self, command):

        if not hasattr(self, "trace"):

            self.trace = []

        self.trace.append(datetime.now(timezone.utc).isoformat() + " TX " + command)

        try:

            self.serial.write((command + "\n").encode("ascii"))

            previous_timeout=getattr(self.serial,'timeout',1)
            try:
                if command in ('RAMHOLD 08 26 FF EF 10000 RESTORE','ENHOLD 08 88 89 88 48 10000 RESTORE','RELOAD 08 71 20 24 D0 20','COMMIT 08 USER'):self.serial.timeout=15 if command.endswith('10000 RESTORE') else 5
                raw = self.serial.read_until(b"\n", 256)
            finally:
                self.serial.timeout=previous_timeout

            if not raw.endswith(b"\n"):

                raise TimeoutError("Resposta incompleta. Reconecte o Pico.")

            response = raw.decode("ascii").strip()

            self.trace.append(datetime.now(timezone.utc).isoformat() + " RX " + response)

            if response in RECOVERABLE:

                raise TargetRejected(response)

            if not response.startswith("OK "):

                raise RuntimeError(response)

            return response

        except TargetRejected:

            raise

        except Exception:

            self.close()

            raise



    def read(self, address, register):

        if address not in ADDRESSES or not 0 <= register <= 255:

            raise ValueError("Endereço de 7 bits ou registrador inválido.")

        result = self.request(f"READ {address:02X} {register:02X}")

        if not re.fullmatch(r"OK [0-9A-Fa-f]{2}", result):

            self.close()

            raise RuntimeError("Resposta de leitura inválida.")

        return int(result[3:],16)



    def probe(self, address):

        if self.version < 2:

            raise ValueError("Atualize o UF2 para v0.2: firmware v1 não tem busca.")

        if address not in ADDRESSES:

            raise ValueError("Endereço reservado.")

        result = self.request(f"PROBE {address:02X}")

        if result not in ("OK ACK", "OK NACK"):

            self.close()

            raise RuntimeError("Resposta PROBE inválida.")

        return result == "OK ACK"



    def read_mfr_id(self, address, pec=False):

        if self.version < 3:

            raise ValueError("Atualize o Pico com o UF2 v0.3 para ler MFR_ID.")

        if address not in ADDRESSES:

            raise ValueError("Endereço reservado.")

        try:

            return decode_mfr(self.request(f"MID {address:02X} {int(pec):02X}"), address, pec)

        except TargetRejected:

            raise

        except Exception:

            self.close()

            raise



    def diagnostics_ready(self):

        if self.version < 4: raise ValueError("Atualize o UF2 para v0.4 (protocolo 4).")



    def set_speed(self, khz):

        self.diagnostics_ready()

        if khz not in (10,50,100): raise ValueError("Velocidade inválida.")

        if self.request(f"SPEED {khz:02X}") != f"OK SPEED {khz:02X}":

            self.close()

            raise RuntimeError("Resposta SPEED inválida.")



    def observe(self):

        self.diagnostics_ready()

        result=self.request("LINES")

        m=re.fullmatch(r"OK LINES 10000 (\d+) (\d+) (\d+) ([0-3])",result)

        if not m or any(int(v)>10000 for v in m.groups()[:3]):

            self.close()

            raise ValueError("Resposta LINES inválida.")

        a,b,c,last=map(int,m.groups())

        return dict(samples=10000,sda_low_samples=a,scl_low_samples=b,changes=c,

                    last_sda=bool(last&1),last_scl=bool(last&2),

                    limitation="Amostragem digital ~100 ms; não mede tensão nem garante ausência de outro mestre")



    def pm_read(self,address,command,pec=False,split=False):

        self.diagnostics_ready()

        if address not in ADDRESSES or command not in COMMANDS or (pec and split):

            raise ValueError("Parâmetros PMBus inválidos; PEC exige repeated START.")

        result=self.request(f"PM {address:02X} {command:02X} {int(pec):02X} {int(split):02X}")

        try:

            return decode_mfr(result,address,pec,command)

        except ValueError as exc:

            # The full serial frame arrived; allow the report to retain this failure.

            raise TargetRejected(str(exc)) from exc



    def register_read(self,address,register):
        from .registers import decode_register
        if self.version<6:raise ValueError("Atualize o UF2 para v0.6")
        if address not in ADDRESSES or not 0<=register<=255:raise ValueError("Parâmetros inválidos")
        return decode_register(self.request(f"REG {address:02X} {register:02X}"),address)

    def telemetry_read(self,address,command):

        from .telemetry import FIELDS,decode_fixed

        if self.version<5:raise ValueError("Atualize o UF2 para v0.5 (protocolo 5).")

        if address not in ADDRESSES or command not in FIELDS:raise ValueError("Comando de telemetria inválido")

        return decode_fixed(self.request(f"TEL {address:02X} {command:02X}"),address,command)



    def raw_read(self,address,register,length=1,split=False):

        self.diagnostics_ready()

        if address not in ADDRESSES or not 0<=register<=255 or length not in (1,2):

            raise ValueError("Parâmetros RAW inválidos.")

        response=self.request(f"RAW {address:02X} {register:02X} {length:02X} {int(split):02X}")

        m=re.fullmatch(r"OK BLOCK ([0-9A-F]{2}) ([0-9A-F]+) --",response)

        if not m or int(m[1],16)!=length or len(m[2])!=length*2:

            raise TargetRejected("Resposta RAW malformada.")

        return dict(raw_hex=m[2],register_hex=f"{register:02X}",length=length,

                    identification="RAW: sem interpretação de registrador, unidade ou ordem dos bytes")



    def drain_trace(self):

        lines, self.trace = self.trace, []

        return lines



    def close(self):

        self.serial.close()



class Simulated:

    version = 6

    def __init__(self, entries):

        self.values = {e.address:e.value for e in entries}

    def read(self,address,register):
        if address==8:return register^0x55  # Explicit synthetic direct-I2C target for crosscheck.

        if address != 0x30:

            raise ValueError("Simulação: endereço sem resposta.")

        if register not in self.values:

            raise ValueError("Registrador ausente da simulação.")

        return self.values[register]

    def probe(self,address):

        return address in (0x30,0x50)

    def read_mfr_id(self,address,pec=False):

        if address != 0x30:

            raise ValueError("Simulação: MFR_ID disponível em 0x30.")

        data = b"SIMULATED"

        checksum = crc8(bytes([address << 1,0x99,address << 1 | 1,len(data)]) + data)

        return decode_mfr(f"OK BLOCK 09 {data.hex().upper()} " + (f"{checksum:02X}" if pec else "--"), address, pec)

    def diagnostics_ready(self): pass

    def set_speed(self,khz):

        if khz not in (10,50,100):raise ValueError("Velocidade inválida")

    def observe(self):

        return dict(samples=10000,sda_low_samples=0,scl_low_samples=0,changes=0,

                    last_sda=True,last_scl=True,limitation="SIMULAÇÃO")

    def pm_read(self,address,command,pec=False,split=False):

        if address!=0x30:raise TargetRejected("ERR PMBUS_COMMAND")

        return dict(command=COMMANDS[command],raw_hex={0x98:"12",0x9A:"44",0x9B:"05"}.get(command,"53494D"),

                    text="SIMULAÇÃO",pec_verified=pec,identification="Simulado; não é identificação real")

    def register_read(self,address,register):
        if address!=0x30:raise TargetRejected("ERR PMBUS_ADDR_W")
        return dict(value=(register^0x55),raw_hex=f"{register^0x55:02X}",pec_verified=True)
    def telemetry_read(self,address,command):

        from .telemetry import FIELDS

        if address!=0x30:raise TargetRejected("ERR PMBUS_ADDR_W")

        values={0xD6:0x88,0x19:0xB0,0x20:0x17,0x88:12,0x89:2,0x8B:512,0x8C:20,0x8D:45,0x8E:40,0x96:20,0x97:24}

        value=values.get(command,0)

        return dict(raw_hex=value.to_bytes(FIELDS[command][1],'little').hex().upper(),

                    value_raw=value,pec_verified=True,pec_received=None,pec_expected=None)

    def raw_read(self,address,register,length=1,split=False):

        if address!=0x30:raise TargetRejected("ERR PMBUS_ADDR_W")

        return dict(raw_hex="00"*length,register_hex=f"{register:02X}",length=length,identification="SIMULAÇÃO")

    def drain_trace(self):

        return []

    def close(self):

        pass


