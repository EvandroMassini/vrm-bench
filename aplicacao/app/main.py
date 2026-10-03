import sys
import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QPushButton,QComboBox,QLineEdit,QLabel,QTableWidget,QTableWidgetItem,QFileDialog,
    QMessageBox,QPlainTextEdit,QCheckBox,QProgressBar,QTabWidget)
from .core import parse_config,compare,region,read_plan
from .transport import Pico,Simulated,serial_ports,identify,ADDRESSES,TargetRejected,COMMANDS,port_caption
from .scan import scan_bus
from .diagnostics import diagnose,addresses_from_text
from .telemetry import collect,FIELDS
from .registers import map_interface,capture as capture_registers,parse_registers

ROOT=Path(__file__).resolve().parents[1]
CAPTURES=(Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else ROOT)/"captures"
BOARD_ALERT=("A leitura não obteve resposta do controlador. A conexão com o Pico não confirma que a placa está alimentada.\n\n"
             "Confirme se a placa está energizada, com GND comum e SDA/SCL ligados, e tente a leitura outra vez.")

def application_icon():
    path=ROOT/"assets"/"vrmbench.ico"
    return QIcon(str(path)) if path.exists() else QIcon()

def board_did_not_answer(text):
    text=str(text)
    return any(part in text for part in ("alimentação da placa","Não foi possível confirmar resposta do CI","BUS_","ERR PMBUS_ADDR","Modelo diferente"))

from .dashboard import DashboardMixin, TELEMETRY_NAMES

class Window(DashboardMixin,QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VRM Bench 0.48 — painel de controle")
        self.setWindowIcon(application_icon())
        from .parameters import set_overwrite_prompt
        set_overwrite_prompt(self.ask_overwrite)
        self.resize(1280,900)
        self.entries,self.capture,self.link=[],None,None
        self.scan_result=None
        self.identity_result=None
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.pending=None
        self.work_generation=0
        self.wait_cursor=False
        self.cancelled=threading.Event()
        self.events=queue.Queue()
        self.ports=[]
        self.use_simulation=False
        from .ui import build_ui
        build_ui(self)
        for signal in (self.profile.currentTextChanged,self.port.currentTextChanged):
            signal.connect(self.invalidate)
        self.profile.currentTextChanged.connect(self.profile_changed)
        self.address.textChanged.connect(self.clear_capture)
        self.direct_address.textChanged.connect(self.clear_capture)
        self.timer=QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(50)
        self.refresh_ports()
        self.note("Pronto. Pico USB selecionado. Nenhuma porta foi aberta automaticamente.")

    def button(self,row,label,fn):
        b=QPushButton(label)
        b.clicked.connect(fn)
        row.addWidget(b)
        self.controls.append(b)
        return b

    def note(self,text):
        from .bus_health import explanation
        guidance=explanation(text)
        if guidance and guidance not in text:text+='\n'+guidance
        stamp=datetime.now().astimezone().isoformat(timespec="seconds")
        self.log.appendPlainText(f"{stamp} {text}")

    def clear_capture(self,*_):
        self.reset_dashboard()
        self.capture=None
        self.identity_result=None
        self.telemetry_table.setRowCount(0)
        if hasattr(self,'register_log'):self.register_log.clear()
        self.render()

    def invalidate(self,*_):
        self.reset_dashboard()
        if self.link: self.link.close()
        self.link=None
        self.capture=None
        self.scan_result=None
        self.identity_result=None
        self.telemetry_table.setRowCount(0)
        if hasattr(self,'found'):self.found.clear()
        self.progress.setValue(0)
        self.status.setText("Pico desconectado | CI não identificado")
        self.render()

    def mode_name(self):
        return 'SIMULAÇÃO' if self.use_simulation else 'Pico USB'

    def chip(self):
        from .controller_store import get
        return get(self.profile.currentText())

    def pmbus(self):
        return int(self.chip()['bus']['pmbus'],16)

    def direct(self):
        return int(self.chip()['bus']['direct'],16)

    def require_selected_controller(self):
        from .controller_store import names
        if self.profile.currentText() not in names():
            raise ValueError('Selecione o CI correto na lista Controlador antes de ler a placa.')

    def require_pico_controller(self):
        self.require_selected_controller()
        if self.use_simulation:
            raise ValueError('Esta operação usa o Pico.')

    def profile_changed(self,*_):
        from .controller_store import select
        self.work_generation+=1
        self.cancelled.set()
        self.entries=[]
        while not self.events.empty():
            try:self.events.get_nowait()
            except queue.Empty:break
        try:
            chip=select(self.profile.currentText())
        except KeyError:
            chip=None
        if chip and hasattr(self,'address'):
            self.address.setText(chip['bus']['pmbus'])
            self.direct_address.setText(chip['bus']['direct'])
        if hasattr(self,'register'):self.register.setText(chip['bus']['register'] if chip else '')
        if hasattr(self,'preset'):self.apply_preset()
        if hasattr(self,'live_values'):
            self.monitor_requested=False;self.monitoring=False;self.monitor_timer.stop();self.collecting_telemetry=False
            self.proposals={};self.live_values={};self.imported_values=None;self.sample_counter=0
            self.telemetry_history.clear();self.telemetry_table.setRowCount(0)
            for values in self.graph_data.values():values.clear()
            for label in self.metric_labels.values():
                label.setText('—');label.setStyleSheet('');label.setToolTip('')
            self.select_chart()
            self.dump_view.clear();self.dump_state.setText('Nenhum dump capturado nesta sessão.')
            self.slots_label.setText('Slots USER: não consultados')
            if chip:
                self.rebuild_parameter_tabs()
                self.editor_state.setText('Parâmetros de '+self.profile.currentText()+' carregados. Leia a placa para preencher os valores atuais.')
            else:
                self.unload_parameters()
                self.editor_state.setText('Selecione o CI para carregar os parâmetros.')
            self.monitor_state.setText('Monitoramento parado.')
        self.render()
        if chip:self.note('Controlador alterado. Atividades do CI anterior foram interrompidas e os parâmetros passaram a ser os do JSON selecionado.')
        else:self.note('Nenhum CI selecionado. Escolha o modelo para carregar os parâmetros.')

    def refresh_ports(self):
        self.invalidate()
        previous=self.port.currentData()
        try:
            self.ports=serial_ports()
        except Exception as exc:
            self.note(f"Falha ao enumerar portas: {exc}")
            return
        self.port.blockSignals(True)
        self.port.clear()
        for p in self.ports:
            self.port.addItem(port_caption(p),p["device"])
        i=self.port.findData(previous)
        if i>=0: self.port.setCurrentIndex(i)
        else:
            candidates=[n for n,p in enumerate(self.ports) if p["vid"]==0x2E8A]
            if len(candidates)==1:self.port.setCurrentIndex(candidates[0])
        self.port.blockSignals(False)
        self.fit_port()
        self.note(f"{len(self.ports)} porta(s) listada(s), sem enviar comandos.")

    def fit_port(self):
        metrics=self.port.fontMetrics()
        sample=metrics.horizontalAdvance('COM7 — Dispositivo Serial USB (COM7)')
        widest=max((metrics.horizontalAdvance(self.port.itemText(i)) for i in range(self.port.count())), default=0)
        self.port.setFixedWidth(max(sample,widest)+40)

    def identify_picos(self):
        self.invalidate()
        ports=list(self.ports)
        def done(result):
            found,failures=result
            for line in failures: self.note(line)
            for p in found: self.note(f'Firmware confirmado: {p["device"]}, protocolo v{p["version"]}, SN:{p["serial"]}')
            if len(found)==1:
                self.port.setCurrentIndex(self.port.findData(found[0]["device"]))
                self.status.setText(f'Pico confirmado em {found[0]["device"]}; clique Conectar | CI não identificado')
            elif len(found)>1:
                self.note("Mais de um Pico confirmado: escolha a COM e clique Conectar.")
            else:
                self.note("Nenhum firmware confirmado entre as portas USB VID 2E8A. Uma porta manual pode ser testada com Conectar.")
        self.run(lambda:identify(ports),done)

    def load(self,path):
        entries=parse_config(Path(path).read_text(encoding="utf-8-sig"))
        self.invalidate()
        self.entries=entries
        self.render()
        self.note(f"Referência: {path} — {len(entries)} entradas; compatibilidade informada pelo usuário.")

    def render(self):
        if not hasattr(self,'table'):return
        values=self.capture["values"] if self.capture else {}
        self.table.setRowCount(len(self.entries))
        for i,e in enumerate(self.entries):
            actual=values.get(f"{e.address:02X}")
            for j,cell in enumerate([f"{e.address:02X}",f"{e.value:02X}",f"{e.mask:02X}",
                                    "—" if actual is None else f"{actual:02X}",compare(e,actual),
                                    region(self.profile.currentText(),e.address)]):
                self.table.setItem(i,j,QTableWidgetItem(cell))
        self.table.resizeColumnsToContents()

    def open_file(self):
        path,_=QFileDialog.getOpenFileName(self,"Configuração",str(ROOT/"samples"),"Texto (*.txt)")
        if path:self.guard(lambda:self.load(path))

    def ask_overwrite(self,path):
        from PySide6.QtCore import QThread
        from .dashboard import confirm
        text=f'O arquivo já existe:\n{path}\n\nSim substitui esse arquivo. Não mantém o arquivo e grava outro nome.'
        if QApplication.instance() is None or QThread.currentThread() is self.thread():
            return confirm(self,'Arquivo existente',text)
        done=threading.Event();answer=[]
        def show():
            answer.append(confirm(self,'Arquivo existente',text));done.set()
        QTimer.singleShot(0,self,show);done.wait()
        return bool(answer and answer[0])
    def guard(self,callback):
        try:callback()
        except Exception as exc:
            self.note(f"ERRO: {exc}")
            QMessageBox.warning(self,"Operação",str(exc))

    def run(self,fn,completed,scanning=False):
        if self.pending:raise ValueError("Aguarde a operação em andamento.")
        if not self.collecting_telemetry:self.suspend_monitoring()
        for c in self.controls:c.setEnabled(False)
        self.stop.setEnabled(scanning)
        link=self.link
        profile=self.profile.currentText()
        address=self.target_address() if link else None
        def checked_job():
            if link:
                from .target_health import verify_target
                verify_target(link,address,profile)
            return fn()
        self.pending=(self.pool.submit(checked_job),completed,self.work_generation)
        if not self.monitoring:self.begin_wait_cursor()

    def poll(self):
        self.telemetry_table.setUpdatesEnabled(False)
        stale=self.pending is not None and len(self.pending)>2 and self.pending[2]!=self.work_generation
        while not self.events.empty():
            event=self.events.get_nowait()
            if stale:continue
            if isinstance(event,dict):
                if 'dump_progress' in event:
                    self.progress.setRange(0,event['dump_total'])
                    self.progress.setValue(event['dump_progress'])
                    continue
                if 'sample' not in event:self.progress.setValue(self.progress.value()+1)
                if 'sample' in event:
                    if self.telemetry_table.rowCount()>=300:self.telemetry_table.removeRow(0)
                    i=self.telemetry_table.rowCount()
                    self.telemetry_table.insertRow(i)
                    cells=[event['sample'],TELEMETRY_NAMES.get(event['command_hex'],event['name']),event.get('raw_hex','—'),
                           event.get('display','—'),'OK' if event.get('pec_verified') else '—']
                    for j,value in enumerate(cells):self.telemetry_table.setItem(i,j,QTableWidgetItem(str(value)))
                    self.update_metric(event)
                    self.telemetry_table.scrollToBottom()
                if 'pass_number' in event and 'pmbus' in event:
                    self.register_log.appendPlainText(f'Passagem {event["pass_number"]} | {event["register_hex"]} | PMBus {event["pmbus"].get("raw_hex","—")} | I²C {event.get("direct",{}).get("raw_hex","—")} | iguais={event.get("equal","—")}')
                elif 'pass_number' in event:
                    self.register_log.appendPlainText(f'Passagem {event["pass_number"]} | registrador {event["register_hex"]} | valor {event.get("raw_hex","—")} | {event.get("error","PEC OK" if event.get("pec_verified") else "PEC não confirmado")}')
                if 'sample' not in event:self.note(json.dumps(event,ensure_ascii=False))
                continue
            checked,address,ack=event
            self.progress.setValue(checked)
            if ack:self.note(f"ACK em 0x{address:02X}: dispositivo não identificado")
        self.telemetry_table.setUpdatesEnabled(True)
        if not self.pending or not self.pending[0].done():return
        future,completed=self.pending[0],self.pending[1]
        generation=self.pending[2] if len(self.pending)>2 else self.work_generation
        self.pending=None
        self.end_wait_cursor()
        for c in self.controls:c.setEnabled(True)
        self.stop.setEnabled(False)
        if generation!=self.work_generation:
            self.collecting_telemetry=False
            self.telemetry_table.setUpdatesEnabled(True)
            return
        if self.link:
            for line in self.link.drain_trace():self.note(line)
        try:completed(future.result())
        except TargetRejected as exc:
            self.identity_result=dict(kind="target_rejected",error=str(exc),source=self.mode_name(),
                                      address_hex=self.address.text(),timestamp_utc=datetime.now(timezone.utc).isoformat())
            self.note(f"Alvo rejeitou a leitura: {exc}. USB permanece conectado.")
            self.status.setText("Pico conectado | Alvo rejeitou leitura; consulte o log")
            self.announce_read_failure(exc)
        except Exception as exc:
            if board_did_not_answer(exc):
                self.note(f"ERRO: {exc}")
                self.status.setText("Pico conectado | A placa não respondeu; confirme se está energizada")
                self.announce_read_failure(exc)
            else:
                self.invalidate()
                self.note(f"ERRO: {exc}. Reconecte.")
                QMessageBox.warning(self,"Operação",str(exc))
        finally:
            if not self.pending:self.resume_monitoring_if_needed()

    def connect(self):
        self.invalidate()
        simulated=self.mode_name()=="SIMULAÇÃO"
        port=self.port.currentText().split(" — ",1)[0].strip()
        entries=list(self.entries)
        def done(link):
            self.link=link
            for line in link.drain_trace():self.note(line)
            self.status.setText(f'{"SIMULAÇÃO" if simulated else "Pico conectado"} — protocolo v{link.version} | CI não identificado')
            self.note(self.status.text())
            if link.version<2:self.note("Firmware v1: leitura disponível; atualize UF2 para busca.")
        self.run(lambda:Simulated(entries) if simulated else Pico(port),done)

    def begin_wait_cursor(self):
        if self.wait_cursor:return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.wait_cursor=True
    def end_wait_cursor(self):
        if not self.wait_cursor:return
        QApplication.restoreOverrideCursor()
        self.wait_cursor=False

    def announce_read_failure(self,exc):
        text=str(exc)
        if board_did_not_answer(text):
            QMessageBox.warning(self,"Placa",BOARD_ALERT+"\n\nDetalhe: "+text)
        else:
            QMessageBox.warning(self,"Operação",text)

    def check_bus(self):
        if not self.link:raise ValueError("Conecte primeiro.")
        if self.mode_name()=="Pico USB" and not self.bus_ready.isChecked():
            raise ValueError("O acesso I²C está bloqueado até a conferência do barramento. Confira 3,3 V, GND comum e nenhum outro mestre ativo. Marque o checkbox «Barramento conferido: 3,3 V • GND comum • nenhum outro mestre ativo».")

    def start_scan(self):
        self.guard(self.scan)

    def scan(self):
        self.check_bus()
        self.require_selected_controller()
        if self.link.version<2:raise ValueError("Busca exige o firmware v0.2 (protocolo 2).")
        self.cancelled.clear()
        self.progress.setRange(0,len(ADDRESSES))
        self.progress.setValue(0)
        if hasattr(self,'found'):self.found.clear()
        self.capture=None
        self.scan_result=None
        self.clear_capture()
        self.status.setText("Buscando ACKs — CI não identificado")
        link=self.link
        source=self.mode_name()
        khz=int(self.speed.currentText().split()[0])
        def execute():
            if link.version>=4:link.set_speed(khz)
            return scan_bus(link,self.cancelled,lambda *v:self.events.put(v))
        self.run(execute,
                 lambda result:self.scan_done(result,source),True)

    def scan_done(self,result,source):
        result.update(source=source,timestamp_utc=datetime.now(timezone.utc).isoformat(),
                      identity="ACK não identifica fabricante, modelo ou interface I2C/PMBus")
        self.scan_result=result
        self.found.blockSignals(True) if hasattr(self,'found') else None
        if hasattr(self,'found'):
            for a in result["addresses"]:self.found.addItem(f"0x{a:02X} — não identificado",a)
            self.found.setCurrentIndex(-1)
            self.found.blockSignals(False)
        end="concluída" if result["complete"] else "cancelada" if result["cancelled"] else "interrompida"
        if result["error"]:
            if self.link:self.link.close()
            self.link=None
        connection="desconectado" if self.link is None else "conectado"
        self.status.setText(f'{source} {connection} | Busca {end}: {len(result["addresses"])} ACK(s) | CI não identificado')
        self.note(json.dumps(result,ensure_ascii=False))
        # Require explicit address selection, even for a single ACK.

    def apply_preset(self,*_):
        self.reg_confirm.setChecked(False)
        from .controller_store import names
        if self.profile.currentText() not in names():
            self.reg_list.clear();self.reg_reference.clear();return
        from .ui import REFERENCE
        index=self.preset.currentIndex()
        from .catalog import INITIAL,EXTENDED
        self.reg_list.setText([INITIAL,'0D','',EXTENDED][index])
        self.reg_reference.setText(REFERENCE if index!=2 else '')

    @staticmethod
    def hex_byte(field,label):
        value=field.text().strip()
        try:
            if not value:raise ValueError()
            result=int(value,16)
            if not 0<=result<=255:raise ValueError()
            return result
        except ValueError:
            raise ValueError(f'{label}: informe um byte hexadecimal, por exemplo 0D.') from None

    def target_address(self,field=None):
        field=self.address if field is None else field
        label='Endereço PMBus' if field is self.address else 'Endereço I²C direto'
        a=self.hex_byte(field,label)
        if a not in ADDRESSES:raise ValueError(f'{label}: use endereço de 7 bits entre 08 e 77, exceto 0C.')
        return a

    def read_config(self):
        self.guard(lambda:self.acquire(read_plan(self.profile.currentText(),self.entries)))

    def read_manufacturer(self):
        def start():
            self.check_bus()
            self.require_selected_controller()
            address=self.target_address()
            link=self.link
            if link.version < 3:
                raise ValueError("Atualize o Pico com o UF2 v0.3 para ler MFR_ID.")
            pec=self.pec.isChecked()
            source=self.mode_name()
            khz=int(self.speed.currentText().split()[0])
            self.clear_capture()
            self.scan_result=None
            def done(result):
                result.update(address_7bit=address,source=source,
                              timestamp_utc=datetime.now(timezone.utc).isoformat())
                self.identity_result=result
                self.status.setText(f'{source} | MFR_ID em 0x{address:02X}: {result["text"]} | Modelo não confirmado')
                self.note(json.dumps(result,ensure_ascii=False))
            def execute():
                if link.version>=4:link.set_speed(khz)
                return link.read_mfr_id(address,pec)
            self.run(execute,done)
        self.guard(start)

    def use_found(self):
        addresses=[self.found.itemData(i) for i in range(self.found.count())]
        self.targets.setText(" ".join(f"{a:02X}" for a in addresses))

    def register_preflight(self):
        self.check_bus()
        self.require_selected_controller()
        if self.link.version<6:raise ValueError('Atualize o UF2 para v0.6 (protocolo 6)')
        return self.target_address(),int(self.speed.currentText().split()[0])

    def map_register_interface(self):
        def start():
            address,khz=self.register_preflight()
            link,source=self.link,self.mode_name()
            self.clear_capture();self.scan_result=None
            self.register_log.clear()
            def done(result):
                result['source']=source;self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False)
                self.register_log.setPlainText(f'Endereço I²C direto: {result["direct_i2c_address_7bit"]:02X}\nInterface habilitada: {"sim" if result["direct_i2c_enabled"] else "não"}\nOs campos do topo não foram alterados. Relatório completo disponível em Exportar último resultado.')
                self.note(text)
                self.status.setText(f'{source} | D6: I²C direto {result["direct_i2c_address_7bit"]:02X}; habilitado={result["direct_i2c_enabled"]}')
            self.run(lambda:map_interface(link,address,khz),done)
        self.guard(start)

    def start_register_capture(self):
        def start():
            address,khz=self.register_preflight()
            registers=parse_registers(self.reg_list.text())
            reference=self.reg_reference.text().strip()
            if not reference or not self.reg_confirm.isChecked():raise ValueError('Informe e verifique a origem dos registradores antes da captura.')
            link,source=self.link,self.mode_name()
            self.clear_capture();self.scan_result=None;self.register_log.clear()
            self.cancelled.clear();self.progress.setRange(0,len(registers)*2);self.progress.setValue(0)
            def done(result):
                result['source']=source;self.identity_result=result
                if result['error']:link.close();self.link=None
                text=json.dumps(result,indent=2,ensure_ascii=False)
                summary='\nComparação das duas passagens:\n'
                for item in result['comparison']:
                    summary+=f'{item["register_hex"]}: {item["first"]} / {item["second"]} — {"iguais" if item["equal"] else "DIFERENTES"}\n'
                summary+=(f'Erro: {result["error"]}\n'+result.get('guidance','')+'\n') if result['error'] else ''
                summary+='Captura parcial; exporte o JSON para análise.'
                self.register_log.appendPlainText(summary);self.note(text)
                self.status.setText(f'{source} | Captura completa={result["complete"]}; passagens iguais={result.get("all_equal","—")}; não é backup MTP')
            self.run(lambda:capture_registers(link,address,khz,registers,reference,self.cancelled,self.events.put),done,True)
        self.guard(start)

    def start_crosscheck(self):
        def start():
            from .crosscheck import compare_paths
            address,khz=self.register_preflight()
            direct=self.target_address(self.direct_address)
            registers=parse_registers(self.reg_list.text())
            reference=self.reg_reference.text().strip()
            if not reference or not self.reg_confirm.isChecked():raise ValueError('Confira a lista e marque a confirmação do ponteiro D3.')
            link,source=self.link,self.mode_name()
            self.clear_capture();self.scan_result=None;self.cancelled.clear()
            self.progress.setRange(0,len(registers)*2);self.progress.setValue(0)
            def done(result):
                result['source']=source;self.identity_result=result
                if result.get('write_attempted') is False:
                    self.status.setText('Teste interrompido antes da escrita | restauração não necessária | exporte o resultado')
                if result['error']:
                    link.close();self.link=None
                    self.register_log.appendPlainText(result['error']+'\n'+result.get('guidance',''))
                else:
                    for item in result['comparison']:
                        from .catalog import LABELS
                        label=LABELS.get(int(item['register_hex'],16),'Registrador manual')
                        self.register_log.appendPlainText(f'{item["register_hex"]} ({label}): '+ ' / '.join(item['values_hex'])+f' | iguais={item["equal"]}')
                self.status.setText(f'Comparação completa={result["complete"]} | quatro valores iguais={result.get("all_equal","—")} | '+('Reconecte após verificar o erro' if result['error'] else 'Exporte o resultado'))
                self.note(json.dumps(result,ensure_ascii=False))
            self.run(lambda:compare_paths(link,address,direct,khz,registers,reference,self.cancelled,self.events.put),done,True)
        self.guard(start)

    def start_telemetry(self,cycles):
        self.collect_telemetry(cycles)

    def read_raw(self):
        def start():
            self.check_bus()
            self.link.diagnostics_ready()
            address=self.target_address(self.direct_address)
            register=self.hex_byte(self.register,"Registrador interno")
            if not 0<=register<=255:raise ValueError("Registrador inválido.")
            length=self.raw_length.currentIndex()+1
            split=self.raw_split.isChecked()
            khz=int(self.speed.currentText().split()[0])
            link,source=self.link,self.mode_name()
            self.clear_capture()
            self.scan_result=None
            def execute():
                link.set_speed(khz)
                return link.raw_read(address,register,length,split)
            def done(result):
                result.update(kind="raw_gpio",source=source,address_7bit=address,khz_nominal=khz,
                              split=split,timestamp_utc=datetime.now(timezone.utc).isoformat())
                self.identity_result=result
                self.note(json.dumps(result,ensure_ascii=False))
                self.status.setText(f'{source} | RAW 0x{register:02X}: {result["raw_hex"]}; sem interpretação')
            self.run(execute,done)
        self.guard(start)

    def use_all(self):
        self.targets.setText(" ".join(f"{a:02X}" for a in ADDRESSES))
        self.note("Lista ampliada para 111 endereços. Nada enviado; revise os comandos antes de Executar sequência.")

    def observe_bus(self):
        def start():
            if not self.link:raise ValueError("Conecte primeiro.")
            self.link.diagnostics_ready()
            link=self.link
            source=self.mode_name()
            self.clear_capture()
            self.scan_result=None
            def done(result):
                result.update(kind="line_observation",source=source,timestamp_utc=datetime.now(timezone.utc).isoformat())
                self.identity_result=result
                self.note(json.dumps(result,ensure_ascii=False))
                self.status.setText(f'{source} | SDA baixo: {result["sda_low_samples"]}; SCL baixo: {result["scl_low_samples"]}; mudanças: {result["changes"]}')
            self.run(link.observe,done)
        self.guard(start)

    def start_diagnostics(self):
        def start():
            self.check_bus()
            self.link.diagnostics_ready()
            addresses=addresses_from_text(self.targets.text())
            commands=[c for c,b in self.command_boxes.items() if b.isChecked()]
            if not commands:raise ValueError("Selecione ao menos um comando.")
            pec,split=self.pec.isChecked(),self.split.isChecked()
            if pec and split:raise ValueError("Desmarque PEC para usar STOP intermediário.")
            khz=int(self.speed.currentText().split()[0])
            link,source=self.link,self.mode_name()
            self.clear_capture()
            self.scan_result=None
            self.cancelled.clear()
            self.progress.setRange(0,len(addresses)*len(commands))
            self.progress.setValue(0)
            self.note(f"Sequência: {len(addresses)} endereço(s), comandos {commands}, {khz} kHz, PEC={pec}, STOP={split}")
            def done(result):
                result['source']=source
                self.identity_result=result
                if result['error']:
                    link.close()
                    self.link=None
                count=sum(r['status']=='response' for r in result['results'])
                end="concluída" if result['complete'] else "cancelada" if result['cancelled'] else "interrompida"
                self.status.setText(f'{source} | Sequência {end}: {count} resposta(s), {len(result["results"])} tentativa(s); modelo não confirmado')
                self.note(json.dumps(result,ensure_ascii=False))
            self.run(lambda:diagnose(link,addresses,commands,khz,pec,split,self.cancelled,self.events.put),done,True)
        self.guard(start)

    def read_single(self):
        def start():
            r=self.hex_byte(self.register,"Registrador interno")
            if not 0<=r<=255:raise ValueError("Registrador deve ter um byte.")
            self.acquire([r])
        self.guard(start)

    def acquire(self,registers):
        self.check_bus()
        address=self.target_address(self.direct_address)
        link=self.link
        metadata=dict(profile=self.profile.currentText(),source=self.mode_name(),
                      address_7bit=address,timestamp_utc=datetime.now(timezone.utc).isoformat(),
                      values={},identification="modelo selecionado, não autenticado")
        self.clear_capture()
        self.scan_result=None
        khz=int(self.speed.currentText().split()[0])
        def read():
            if link.version>=4:link.set_speed(khz)
            for r in registers:metadata["values"][f"{r:02X}"]=link.read(address,r)
            return metadata
        def done(capture):
            self.capture=capture
            self.render()
            self.status.setText(f'{capture["source"]} conectado | Leitura em 0x{address:02X} concluída; CI não identificado')
            self.note(json.dumps(capture,ensure_ascii=False))
        self.run(read,done)

    def choose_report_reference(self):
        def action():
            path,_=QFileDialog.getOpenFileName(self,'Referência apenas para comparação',str(ROOT/'samples'),'TXT (*.txt)')
            if not path:return
            self.report_reference=parse_config(Path(path).read_text(encoding='utf-8-sig'))
            self.report_reference_label.setText(path+' — comparação, nunca aplicado à placa')
        self.guard(action)

    def render_report(self,result):
        self.clear_capture();self.scan_result=None;self.identity_result=result
        rows=result['rows'];self.report_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,key in enumerate(('register','loop','field','bits','value','reference','comparison','engineering','conversion_source')):
                self.report_table.setItem(i,j,QTableWidgetItem('—' if row[key] is None else str(row[key])))
        self.report_table.resizeColumnsToContents()
        self.report_note.setText(('PARCIAL: '+result['error'] if result.get('error') else 'Análise concluída')+' | '+result.get('backup_path','Arquivo offline; sem acesso ao Pico'))
        self.note(self.report_note.text())

    def start_report(self):
        def start():
            from .report import collect
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus() or self.target_address(self.direct_address)!=self.direct():raise ValueError('Use PMBus 70 e I²C 08')
            link=self.link;reference=getattr(self,'report_reference',[])
            self.run(lambda:collect(link,CAPTURES/'backups',reference),self.render_report)
        self.guard(start)

    def open_report_json(self):
        def action():
            from .report import analyze
            path,_=QFileDialog.getOpenFileName(self,'Captura de offsets ou relatório',str(CAPTURES),'JSON (*.json)')
            if not path:return
            result=json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if result.get('kind') not in ('offset_snapshot','parameter_report','user_preparation_capture'):raise ValueError('Selecione um snapshot de offsets 0.14 ou relatório consolidado.')
            from .core import Entry
            reference=getattr(self,'report_reference',None)
            if reference is None:reference=[Entry(**e) for e in result.get('reference_entries',[])]
            result['reference_entries']=[dict(address=e.address,value=e.value,mask=e.mask) for e in reference]
            result['rows']=analyze(result['values'],reference)
            result['offline_source']=path
            self.render_report(result)
        self.guard(action)

    def read_parameters(self):
        def start():
            from .parameters import snapshot
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus() or self.target_address(self.direct_address)!=self.direct():raise ValueError('Use PMBus 70 e I²C 08.')
            link=self.link
            self.clear_capture();self.scan_result=None
            def done(result):
                self.identity_result=result
                self.offset_table.setRowCount(2)
                for i,item in enumerate(result['loops']):
                    values=[str(item['loop']),item['raw_hex'],str(item['signed_code']),
                            'E (ensaio FF → EF → FF)' if i==0 else 'Preservado']
                    for j,value in enumerate(values):self.offset_table.setItem(i,j,QTableWidgetItem(value))
                self.offset_log.setPlainText(json.dumps(result,indent=2,ensure_ascii=False))
                self.status.setText('Leitura concluída | backup parcial salvo | nenhuma configuração alterada')
                self.note('Backup parcial salvo: '+result['backup_path'])
            self.run(lambda:snapshot(link,CAPTURES/'backups'),done)
        self.guard(start)

    def start_user_capture(self):
        def start():
            from .user_capture import collect
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus():raise ValueError('Use PMBus 70.')
            link=self.link;self.clear_capture();self.scan_result=None
            def done(result):
                self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False);self.user_log.setPlainText(text);self.note(text)
                message='Captura completa' if result['complete'] else 'Captura parcial: '+str(result['error'])
                self.status.setText(message+' | programação MTP permanece indisponível | exporte o resultado')
            self.run(lambda:collect(link,CAPTURES/'backups'),done)
        self.guard(start)

    def start_ensoft(self, hold=False):
        def start():
            from .software_enable import experiment
            from .parameters import save_backup
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus() or self.target_address(self.direct_address)!=self.direct():raise ValueError('Este ensaio exige PMBus 70 e I²C 08.')
            if self.link.version!=12:raise ValueError('Atualize o Pico com o UF2 0.21, protocolo 12.')
            if not self.ensoft_confirm.isChecked():raise ValueError('Marque a autorização do ensaio reversível.')
            link=self.link
            self.ensoft_confirm.setChecked(False)
            self.clear_capture();self.scan_result=None;self.enable_log.clear()
            self.note('Ensaio 88/89: código 2 → 1 → 2. Não desconecte a alimentação. Aguarde a restauração.')
            def before(result):
                data=dict(kind='before_software_enable',timestamp_utc=result['timestamp_utc'],
                    scope='Baseline 88/89 antes do ensaio. Não é imagem MTP.',
                    baseline=result['baseline'],mapping=result['mapping'],soft_hex='48',restore_hex='88',
                    hold_requested_ms=result['hold_requested_ms'])
                result['backup_path']=save_backup(data,CAPTURES/'backups')
            def done(result):
                result['source']='Pico USB';self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False);self.enable_log.setPlainText(text);self.note(text)
                if result.get('write_attempted') is False:
                    self.status.setText('Ensaio interrompido antes da escrita | restauração não necessária')
                elif result.get('complete') and result.get('change_confirmed'):
                    self.status.setText('Código 1 confirmado e restauração confirmada | MTP permanece indisponível')
                elif result.get('complete'):
                    self.status.setText('Restauração confirmada | código 1 não comprovado | não repetir em sequência')
                else:
                    self.status.setText('Ensaio não confirmado | confira o relatório antes de religar')
                if result.get('error'):
                    link.close();self.link=None
                    QMessageBox.warning(self,'Enable por software',result['error']+'\n'+result.get('guidance',''))
            self.run(lambda:experiment(link,before,hold=hold),done)
        self.guard(start)

    def start_user_verify(self):
        def start():
            from .verify_user import compare_live
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus():raise ValueError('Use PMBus 70.')
            link=self.link
            self.clear_capture();self.scan_result=None
            def done(result):
                self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False);self.verify_log.setPlainText(text);self.note(text)
                if result.get('complete') and result.get('user_masked_equal'):
                    self.status.setText('USER ativo coincide com a imagem sob a máscara | MTP permanece indisponível')
                elif result.get('complete'):
                    self.status.setText(f'{result["mismatch_count"]} byte(s) fora da máscara | MTP permanece indisponível')
                else:
                    self.status.setText('Comparação incompleta | confira o relatório')
            self.run(lambda:compare_live(link,CAPTURES/'backups'),done)
        self.guard(start)

    def start_config_dump(self):
        def start():
            from .config_dump import capture
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus():raise ValueError('Use PMBus 70.')
            link=self.link
            self.clear_capture();self.scan_result=None;self.dump_log.clear()
            self.progress.setRange(0,260);self.progress.setValue(0)
            def done(result):
                self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False);self.dump_log.setPlainText(text);self.note(text)
                if self.accept_board_read(result, self.fill_parameters):
                    self.status.setText('TXT gravado | este arquivo passa a ser a base do parâmetro | MTP indisponível')
                elif result.get('complete') and not result.get('stable'):
                    self.status.setText('Leitura instável | TXT não gravado | MTP permanece indisponível')
                elif result.get('error') or not result.get('complete'):
                    self.status.setText('Leitura do mapa incompleta | confira o relatório')
                else:
                    self.status.setText('Leitura interrompida | o mapa não corresponde ao CI selecionado')
            self.run(lambda:capture(link,CAPTURES,lambda n,total:self.events.put(dict(dump_progress=n,dump_total=total))),done)
        self.guard(start)

    def start_config_diff(self):
        def start():
            from .config_dump import plan_against_file
            result=self.identity_result
            if not result or result.get('kind')!='config_dump' or not result.get('values'):
                raise ValueError('Leia os parâmetros da placa antes de comparar.')
            path,_=QFileDialog.getOpenFileName(self,'TXT só para comparação',str(ROOT/'samples'),'Texto (*.txt)')
            if not path:return
            plan=plan_against_file(result['values'],Path(path).read_text(encoding='utf-8-sig'))
            plan['reference_path']=path
            text=json.dumps(plan,indent=2,ensure_ascii=False);self.dump_log.setPlainText(text);self.note(text)
            self.status.setText(f'{plan["diverge_count"]} diferença(s) sob a máscara | nenhum byte escrito')
        self.guard(start)

    def fill_parameters(self, values=None):
        from .param_byte import load_baseline, writable
        values = values or load_baseline()
        selected = self.param_register.currentData()
        keep = selected[0] if selected else 0x26
        self.param_register.blockSignals(True)
        self.param_register.clear()
        index = 0
        for i, (address, value) in enumerate(writable(values)):
            self.param_register.addItem(f'{address:02X}   arquivo {value:02X}', (address, value))
            if address == keep:
                index = i
        self.param_register.setCurrentIndex(index)
        self.param_register.blockSignals(False)

    def parameter_baseline(self):
        from .param_byte import load_baseline
        fresh = self.identity_result
        if fresh and fresh.get('kind') == 'config_dump' and fresh.get('stable') and fresh.get('values'):
            return {int(key, 16): int(value, 16) for key, value in fresh['values'].items()}
        return load_baseline()

    def start_param(self, restore):
        def start():
            from .param_byte import change_byte
            self.check_bus()
            self.require_pico_controller()
            if self.target_address() != self.pmbus() or self.target_address(self.direct_address) != self.direct():
                raise ValueError('Use PMBus 70 e I²C 08.')
            if not self.param_confirm.isChecked():
                raise ValueError('Marque a autorização antes de alterar o byte.')
            if not self.link or self.link.version not in (13, 14, 15):
                current = self.link.version if self.link else 'desconhecido'
                raise ValueError(f'O Pico responde protocolo {current}. Este byte em RAM funciona nos protocolos 13, 14 e 15. O UF2 atual é o 0.26, protocolo 15.')
            data = self.param_register.currentData()
            if not data:
                raise ValueError('Escolha um registrador do arquivo.')
            baseline = self.parameter_baseline()
            address = data[0]
            if address not in baseline:
                raise ValueError('O arquivo não tem este registrador.')
            target = baseline[address] if restore else self.hex_byte(self.param_value, 'Valor novo')
            link = self.link
            self.param_confirm.setChecked(False)
            self.param_log.clear()
            def done(result):
                self.param_log.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
                self.note(self.param_log.toPlainText())
                if result.get('complete') and result.get('operation') == 'apply':
                    self.status.setText(f'{address:02X} ficou {target:02X} em RAM | a gravação permanente é a aba Slot USER')
                elif result.get('complete'):
                    self.status.setText(f'{address:02X} voltou ao byte do arquivo | MTP indisponível')
                else:
                    self.status.setText('Parâmetro não confirmado | não repetir sem ler o relatório')
                if result.get('error'):
                    QMessageBox.warning(self, 'Parâmetro em RAM', result['error'] + '\n' + result.get('guidance', ''))
            self.run(lambda: change_byte(link, CAPTURES / 'backups', address, target, baseline), done)
        self.guard(start)

    def start_reenable(self):
        self.reset_dashboard()
        def start():
            from .software_enable import experiment
            self.check_bus()
            self.require_pico_controller()
            if not self.reen_confirm.isChecked():
                raise ValueError('Marque a autorização antes de religar as saídas.')
            if not self.link or self.link.version not in (12, 13, 14, 15):
                current = self.link.version if self.link else 'desconhecido'
                raise ValueError(f'O Pico responde protocolo {current}. Este religamento funciona no protocolo 15.')
            link = self.link
            self.reen_confirm.setChecked(False)
            self.param_log.clear()
            def done(result):
                self.param_log.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
                self.note(self.param_log.toPlainText())
                if result.get('complete'):
                    self.status.setText('Saídas religadas | meça o VCORE de novo | não grave o slot ainda')
                else:
                    self.status.setText('Religamento não confirmado | não repita sem ler o quadro')
                if result.get('error'):
                    QMessageBox.warning(self, 'Saídas', result['error'] + '\n' + result.get('guidance', ''))
            self.run(lambda: experiment(link), done)
        self.guard(start)

    def start_reload(self):
        self.reset_dashboard()
        def start():
            from .reload_mtp import reload_and_read
            self.check_bus()
            self.require_pico_controller()
            if self.target_address() != self.pmbus() or self.target_address(self.direct_address) != self.direct():
                raise ValueError('Use PMBus 70 e I²C 08.')
            if not self.reload_confirm.isChecked():
                raise ValueError('Marque a autorização antes da recarga.')
            if not self.link or self.link.version not in (14, 15):
                current = self.link.version if self.link else 'desconhecido'
                raise ValueError(f'O Pico responde protocolo {current}. A recarga funciona nos protocolos 14 e 15.')
            link = self.link
            self.reload_confirm.setChecked(False)
            self.reload_log.clear()
            def done(result):
                self.reload_log.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
                self.note(self.reload_log.toPlainText())
                if result.get('complete'):
                    self.status.setText('Recarga confirmada | imagem igual ao arquivo desta placa | nenhum slot gravado')
                elif result.get('reload_confirmed'):
                    self.status.setText('Recarga executada | imagem diferente ou instável | nenhum slot gravado')
                else:
                    self.status.setText('Recarga não confirmada | nenhum slot gravado')
                if result.get('error'):
                    QMessageBox.warning(self, 'Recarga MTP', result['error'] + '\n' + result.get('guidance', ''))
            self.run(lambda: reload_and_read(link, CAPTURES / 'backups'), done)
        self.guard(start)

    def start_preview(self):
        def start():
            from .slot_commit import preview_changes
            self.check_bus()
            self.require_pico_controller()
            if not self.link or self.link.version != 15:
                current = self.link.version if self.link else 'desconhecido'
                raise ValueError(f'O Pico responde protocolo {current}. Continue com o UF2 0.26, protocolo 15.')
            link = self.link
            self.change_token = None
            self.commit_log.clear()
            def done(result):
                self.change_token = result.get('image_token') if result.get('complete') and result.get('difference_count') else None
                self.commit_log.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
                self.note(self.commit_log.toPlainText())
                count = result.get('difference_count')
                if result.get('complete') and count:
                    self.status.setText(f'{count} diferença(s) em relação ao arquivo | slot ainda não gravado')
                elif result.get('complete'):
                    self.status.setText('Imagem igual ao arquivo | nenhum slot será gasto')
                else:
                    self.status.setText('Diferenças não lidas')
                if result.get('error'):
                    QMessageBox.warning(self, 'Slot USER', result['error'])
            self.run(lambda: preview_changes(link, CAPTURES / 'backups'), done)
        self.guard(start)

    def start_commit_changed(self):
        def start():
            from .slot_commit import commit_user_slot
            self.check_bus()
            self.require_pico_controller()
            if self.target_address() != self.pmbus() or self.target_address(self.direct_address) != self.direct():
                raise ValueError('Use PMBus 70 e I²C 08.')
            if not self.commit_confirm.isChecked():
                raise ValueError('Marque a autorização antes de gravar o slot.')
            if not getattr(self, 'change_token', None):
                raise ValueError('Leia as diferenças primeiro. A imagem precisa diferir do arquivo.')
            if not self.link or self.link.version != 15:
                current = self.link.version if self.link else 'desconhecido'
                raise ValueError(f'O Pico responde protocolo {current}. Continue com o UF2 0.26, protocolo 15.')
            link = self.link
            token = self.change_token
            self.commit_confirm.setChecked(False)
            self.change_token = None
            self.commit_log.clear()
            def done(result):
                self.commit_log.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
                self.note(self.commit_log.toPlainText())
                if result.get('complete'):
                    left = result.get('user_left_after')
                    self.status.setText(f'Slot USER gravado com a imagem alterada | restam {left}')
                elif result.get('write_attempted') is False:
                    self.status.setText('Slot não gravado | nenhum opcode enviado')
                else:
                    self.status.setText('Gravação não confirmada | não repetir sem ler o relatório')
                if result.get('error'):
                    QMessageBox.warning(self, 'Slot USER', result['error'] + '\n' + result.get('guidance', ''))
            self.run(lambda: commit_user_slot(link, CAPTURES / 'backups', require='changed', image_token_expected=token), done)
        self.guard(start)

    def attach_enable_measurements(self):
        def action():
            import math
            result=self.identity_result
            if not result or result.get('kind')!='software_enable_experiment':raise ValueError('Execute o ensaio de enable antes de anexar as medições.')
            readings=[]
            for edit in (self.enable_before,self.enable_during,self.enable_after):
                value=float(edit.text().strip().replace(',','.'))
                if not math.isfinite(value) or not 0<=value<3:raise ValueError('Informe tensões em volts, de 0 inclusive até menos de 3.')
                readings.append(value)
            result['external_measurements']=dict(source='Multímetro, valores informados pelo usuário; não verificados automaticamente',
                before_v=readings[0],during_v=readings[1],after_v=readings[2],delta_mv=round((readings[1]-readings[0])*1000,4),
                return_delta_mv=round((readings[2]-readings[0])*1000,4))
            from .parameters import save_backup
            path=save_backup(result,CAPTURES/'backups')
            self.enable_log.setPlainText(json.dumps(result,indent=2,ensure_ascii=False));self.note('Relatório com medições salvo: '+path)
        self.guard(action)

    def start_mtp_status(self):
        def start():
            from .mtp_status import inspect
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus():raise ValueError('Use PMBus 70.')
            link=self.link;self.clear_capture();self.scan_result=None
            def done(result):
                self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False);self.mtp_log.setPlainText(text);self.note(text)
                self.status.setText('Indicadores MTP lidos; programação bloqueada.' if result['complete'] else 'Diagnóstico parcial; confira o erro no relatório.')
            self.run(lambda:inspect(link,CAPTURES/'backups'),done)
        self.guard(start)

    def start_ramedit(self,restore):
        def start():
            from .ramedit import change
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus() or self.target_address(self.direct_address)!=self.direct():raise ValueError('Use PMBus 70 e I²C 08.')
            if self.link.version not in (11,12):raise ValueError('Atualize o firmware para 0.18 / protocolo 11 ou 0.21 / protocolo 12.')
            if not restore and not self.edit_confirm.isChecked():raise ValueError('Marque a autorização para manter o offset em RAM.')
            self.edit_confirm.setChecked(False);link=self.link
            self.clear_capture();self.scan_result=None
            self.edit_state.setText('Operação em andamento; aguarde a verificação.')
            def done(result):
                self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False);self.edit_log.setPlainText(text);self.note(text)
                if result['complete']:
                    message='FF confirmado: offset original.' if restore else 'EF confirmado: −6,25 mV permanece em RAM. Use Restaurar FF ao terminar.'
                else:message='Operação não confirmada. Confira o relatório; não repita a aplicação.'
                self.edit_state.setText(message);self.status.setText(message)
                if result.get('error') or result.get('warning') or result.get('save_error'):
                    QMessageBox.warning(self,'Resultado em RAM','\n'.join(str(result[k]) for k in ('error','warning','guidance','save_error') if result.get(k)))
            self.run(lambda:change(link,CAPTURES/'backups',restore),done)
        self.guard(start)

    def start_ramtest(self,hold=False):
        def start():
            from .ramtest import experiment
            self.check_bus()
            self.require_pico_controller()
            if self.target_address()!=self.pmbus() or self.target_address(self.direct_address)!=self.direct():raise ValueError('Este ensaio exige PMBus 70 e I²C 08.')
            if self.link.version not in (9,10,11,12):raise ValueError('Atualize o Pico com o UF2 v0.13 (protocolo 9 RAMTEST).')
            if hold and self.link.version not in (10,11,12):raise ValueError('Atualize para firmware 0.17, protocolo 10.')
            if not self.ram_confirm.isChecked():raise ValueError('Confira e marque a confirmação do ensaio na sucata sem GPU.')
            link=self.link
            self.ram_confirm.setChecked(False)
            self.clear_capture();self.scan_result=None;self.ram_log.clear()
            if hold:self.note('Ensaio de medição: EF será mantido por 10 segundos após confirmação; restauração local automática. Aguarde o resultado.')
            self.note('Ensaio único 26: FF → EF → FF, 100 kHz. Não desconecte a alimentação durante o teste.')
            def done(result):
                result['source']='Pico USB';self.identity_result=result
                text=json.dumps(result,indent=2,ensure_ascii=False);self.ram_log.setPlainText(text);self.note(text)
                self.status.setText(f'Alteração confirmada={result.get("change_confirmed","—")} | restauração={result["restoration_confirmed"]} | exporte o resultado')
                if result.get('write_attempted') is False:
                    self.status.setText('Teste interrompido antes da escrita | restauração não necessária | exporte o resultado')
                if result['error']:
                    link.close();self.link=None
                    QMessageBox.warning(self,'Resultado do ensaio',result['error']+'\n'+result.get('guidance',''))
            from .parameters import backup_before_test
            self.run(lambda:experiment(link,lambda r:backup_before_test(r,CAPTURES/'backups'),hold=hold),done)
        self.guard(start)

    def attach_measurements(self):
        def action():
            import math
            result=self.identity_result
            if not result or result.get('kind')!='ram_write_experiment':raise ValueError('Execute o ensaio antes de anexar as medições.')
            readings=[]
            for edit in (self.voltage_before,self.voltage_during,self.voltage_after):
                value=float(edit.text().strip().replace(',','.'))
                if not math.isfinite(value) or not 0<value<3:raise ValueError('Informe tensões medidas em volts, maiores que zero e menores que 3 V.')
                readings.append(value)
            result['external_measurements']=dict(source='Multímetro, valores informados pelo usuário; não verificados automaticamente',
                before_v=readings[0],during_v=readings[1],after_v=readings[2],delta_mv=round((readings[1]-readings[0])*1000,4),
                return_delta_mv=round((readings[2]-readings[0])*1000,4))
            from .parameters import save_backup
            path=save_backup(result,CAPTURES/'backups')
            self.ram_log.setPlainText(json.dumps(result,indent=2,ensure_ascii=False));self.note('Relatório com medições salvo: '+path)
        self.guard(action)

    def pick_session(self,reference):
        path,_=QFileDialog.getOpenFileName(self,'Selecionar captura',str(CAPTURES),'JSON (*.json)')
        if path:(self.session_reference if reference else self.session_current).setText(path)

    def compare_sessions(self):
        def execute():
            from .sessions import compare_files
            reference,current=self.session_reference.text().strip(),self.session_current.text().strip()
            if not reference or not current:raise ValueError('Selecione o JSON de referência e o JSON da nova captura.')
            result=compare_files(reference,current)
            self.identity_result=result;self.capture=None;self.scan_result=None
            self.session_table.setRowCount(len(result['rows']))
            for i,row in enumerate(result['rows']):
                for j,key in enumerate(('register_hex','reference_hex','current_hex','state')):
                    self.session_table.setItem(i,j,QTableWidgetItem(row[key] or '—'))
            self.session_table.resizeColumnsToContents()
            self.status.setText(f'Comparação de arquivos | alterações: {result["changed_count"]} | ausentes: {result["missing_count"]} | avisos: {len(result["warnings"])}')
            self.note(json.dumps(result,ensure_ascii=False))
        self.guard(execute)

    def export(self):
        data=self.identity_result or self.capture or self.scan_result
        if data is None:
            QMessageBox.information(self,"Resultado","Faça uma busca ou leitura primeiro.")
            return
        CAPTURES.mkdir(parents=True,exist_ok=True)
        filename='comparacao_ampliada_70_08.json' if data.get('kind')=='interface_crosscheck' and data.get('pmbus_address_7bit')==0x70 and data.get('direct_i2c_address_7bit')==8 and len(data.get('requested_registers',[]))==17 else 'resultado.json'
        path,_=QFileDialog.getSaveFileName(self,"Salvar resultado",str(CAPTURES/filename),"JSON (*.json)")
        if path:self.guard(lambda:Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8"))

    def save_log(self):
        CAPTURES.mkdir(parents=True,exist_ok=True)
        path,_=QFileDialog.getSaveFileName(self,"Salvar log",str(CAPTURES/"sessao.txt"),"Texto (*.txt)")
        if path:self.guard(lambda:Path(path).write_text(self.log.toPlainText(),encoding="utf-8"))

    def closeEvent(self,event):
        self.pause_monitoring()
        if not self.pending:self.end_wait_cursor()
        if self.pending:
            self.cancelled.set()
            QMessageBox.information(self,"Operação","Cancelamento solicitado; aguarde a operação terminar.")
            event.ignore()
            return
        if self.link:self.link.close()
        self.pool.shutdown(wait=False)
        event.accept()

def main():
    application=QApplication(sys.argv)
    application.setWindowIcon(application_icon())
    window=Window()
    window.show()
    sys.exit(application.exec())

if __name__=="__main__":main()
