import json, math, time
from collections import deque
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import QTimer, Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QWidget,QLineEdit,QComboBox,QTableWidgetItem,QMessageBox,QFileDialog
from . import editor_model as model

def confirm(parent,title,text):
    """Question dialog with Portuguese buttons. Não is the default."""
    box=QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    no=box.addButton('Não',QMessageBox.ButtonRole.NoRole)
    yes=box.addButton('Sim',QMessageBox.ButtonRole.YesRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes

from .controller_store import current, names
METRICS=tuple((item['key'],item['title'],item['unit']) for item in current()['telemetry']['metrics'])
METRIC_GRID=tuple(tuple(item) for item in current()['telemetry']['metric_grid'])
TELEMETRY_NAMES=current()['telemetry']['names']

class TrendPlot(QWidget):
    def __init__(self):
        super().__init__();self.points=[];self.caption='Tensão de saída • V';self.setMinimumHeight(200)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor('#0f1d30'))
        left,top,width,height=65,32,max(1,self.width()-90),max(1,self.height()-70)
        p.setPen(QColor('#9fb5cf'));p.drawText(14,21,self.caption)
        if not self.points:p.drawText(80,80,'Aguardando medições válidas…');return
        vals=[v for _,v in self.points];lo,hi=min(vals),max(vals);pad=max((hi-lo)*.1,abs(hi)*.001,.001);lo-=pad;hi+=pad
        for i in range(5):
            y=top+height*i/4;p.setPen(QColor('#25364d'));p.drawLine(left,int(y),left+width,int(y))
            p.setPen(QColor('#9fb5cf'));p.drawText(4,int(y+4),f'{hi-(hi-lo)*i/4:.5g}')
        first=self.points[0][0];span=max(self.points[-1][0]-first,1)
        poly=QPolygonF([QPointF(left+(t-first)/span*width,top+(hi-v)/(hi-lo)*height) for t,v in self.points])
        p.setPen(QPen(QColor('#39c8df'),2));p.drawPolyline(poly)
        for pos in poly:p.drawEllipse(pos,2,2)
        p.setPen(QColor('#9fb5cf'));p.drawText(left,top+height+25,f'Amostra {int(first)}');p.drawText(left+width-115,top+height+25,f'Amostra {int(self.points[-1][0])}')

class DashboardMixin:
    def init_dashboard(self):
        self.live_values={};self.proposals={};self.editor_widgets={};self.imported_values=None
        self.monitoring=False;self.monitor_requested=False;self.collecting_telemetry=False;self.sample_counter=0;self.telemetry_history=deque(maxlen=600)
        self.graph_data={k:deque(maxlen=100) for k,_,_ in METRICS}
        self.monitor_timer=QTimer(self);self.monitor_timer.setSingleShot(True);self.monitor_timer.timeout.connect(self.monitor_tick)
        self.tabs.currentChanged.connect(self.telemetry_tab_changed)
        self.render_editor()

    def reset_dashboard(self):
        if not hasattr(self,'live_values'):return
        self.pause_monitoring();self.collecting_telemetry=False;self.sample_counter=0;self.live_values={};self.imported_values=None;self.slots_label.setText('Slots USER: não consultados')
        self.clear_proposals();self.dump_view.clear();self.dump_state.setText('Nenhum dump capturado nesta conexão.')
        self.editor_state.setText('Leia novamente a placa; valores anteriores invalidados.')
        self.telemetry_history.clear()
        for d in self.graph_data.values():d.clear()
        for l in self.metric_labels.values():l.setText('—')
        self.select_chart()

    def render_editor(self):
        old=set(x[1] for x in self.editor_widgets.values());self.controls[:]=[x for x in self.controls if x not in old]
        self.editor_widgets={}
        if self.profile.currentText() not in names():
            for table in self.editor_tables.values():table.setRowCount(0)
            if self.phase_table is not None:self.phase_table.setRowCount(0)
            self.validate_proposals();return
        for group,table in self.editor_tables.items():
            fields=[f for f in model.FIELDS if model.group(f)==group]
            fields.sort(key=lambda f:(not model.editable(f,self.live_values),0 if f['symbol'].endswith('VBOOT') else 1 if f['symbol'].endswith('VID_OFFSET') else 2,model.label(f)))
            table.setRowCount(len(fields))
            for i,f in enumerate(fields):
                reason=model.lock_reason(f,self.live_values)
                table.setRowHeight(i,96 if reason else 43)
                code_item=QTableWidgetItem(f"{f['address']:02X}");code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);code_item.setToolTip(f.get('description') or model.label(f));table.setItem(i,0,code_item)
                name=QTableWidgetItem(model.label(f));name.setToolTip(f.get('description') or model.label(f));table.setItem(i,1,name)
                current=QLineEdit(model.display(f,self.live_values));current.setReadOnly(True);table.setCellWidget(i,2,current)
                edit=self.editor_input(f);table.setCellWidget(i,3,edit);self.controls.append(edit)
                edit.setAccessibleName(group+' '+model.label(f)+' novo valor')
                if reason:edit.setToolTip(reason)
                hint=reason or model.hint(f)
                hint_item=QTableWidgetItem(hint)
                if reason:hint_item.setToolTip(reason)
                table.setItem(i,4,hint_item);self.editor_widgets[f['symbol']]=(f,edit,current)
                if isinstance(edit,QComboBox):
                    edit.currentIndexChanged.connect(lambda _index,s=f['symbol'],box=edit:self.choice_changed(s,box))
                else:
                    edit.textChanged.connect(lambda text,s=f['symbol']:self.proposal_changed(s,text))
        self.validate_proposals();self.refresh_phases()

    def unload_parameters(self):
        old=set(item[1] for item in self.editor_widgets.values());self.controls[:]=[item for item in self.controls if item not in old]
        self.editor_widgets={};self.editor_tables={};self.phase_table=None;self.loop_tabs.clear()

    def make_editor_table(self,headers,layout):
        from PySide6.QtWidgets import QTableWidget,QHeaderView
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers);table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers);table.verticalHeader().hide();table.setWordWrap(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(table,1);return table

    def rebuild_parameter_tabs(self):
        from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel
        old=set(x[1] for x in self.editor_widgets.values());self.controls[:]=[x for x in self.controls if x not in old]
        self.editor_widgets={}
        chip=current()
        present=[]
        for field in chip.get('fields',[]):
            name=field.get('group') or 'Compartilhados'
            if name not in present:present.append(name)
        groups=[name for name in ('Loop 1','Loop 2','Compartilhados') if name in present]
        groups+=[name for name in present if name not in groups]
        self.loop_tabs.clear();self.editor_tables={}
        for name in groups:
            page=QWidget();layout=QVBoxLayout(page);self.loop_tabs.addTab(page,name)
            self.editor_tables[name]=self.make_editor_table(['Código','Parâmetro','Valor atual','Novo valor','Unidade / validação'],layout)
        page=QWidget();layout=QVBoxLayout(page);self.loop_tabs.addTab(page,'Fases')
        phase_note=QLabel('Limites programados, não telemetria. Corrente fora do limite em uma fase desliga o loop. O valor, em 2 A por código, é o mesmo para as fases do loop. O balanceamento é PH1 a PH8. As primeiras fases da contagem oficial ficam no loop 1; as seguintes, no loop 2. Estes números só mudam com nova leitura ou gravação de parâmetros.')
        phase_note.setWordWrap(True);phase_note.setObjectName('muted');layout.addWidget(phase_note)
        self.phase_table=self.make_editor_table(['Código','Fase','Loop','Sobrecorrente rápida por fase','Sobrecorrente lenta por fase','Balanceamento'],layout)
        self.phase_state=QLabel('Aguardando leitura. Use Ler valores atuais ou Ler placa.');self.phase_state.setWordWrap(True);self.phase_state.setObjectName('muted');layout.addWidget(self.phase_state)
        self.render_editor()

    def editor_input(self,f):
        choices=f.get('choices') or []
        can=model.editable(f,self.live_values) and any('code' in choice for choice in choices)
        if f.get('widget')=='select' and choices:
            box=QComboBox();box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            if can:box.addItem('Manter atual',None)
            for choice in choices:
                box.addItem(choice['text'],choice.get('code'))
            proposal=self.proposals.get(f['symbol'])
            if isinstance(proposal,int):
                index=box.findData(proposal)
            elif isinstance(proposal,str) and proposal.strip():
                index=box.findText(proposal.strip())
            elif not can and f['address'] in self.live_values:
                shown=model.display(f,self.live_values)
                index=box.findText(shown)
                if index<0 and shown not in ('Conversão não validada','Não lido'):
                    index=box.findData(model.code(f,self.live_values))
            else:
                index=0 if can else -1
            box.setCurrentIndex(index if index is not None and index>=0 else (-1 if not can else 0))
            box.setEnabled(can)
            return box
        edit=QLineEdit('' if not isinstance(self.proposals.get(f['symbol']),str) else self.proposals.get(f['symbol'],''))
        edit.setReadOnly(not model.editable(f,self.live_values))
        edit.setPlaceholderText('Manter atual' if model.editable(f,self.live_values) else '—')
        return edit

    def choice_changed(self,s,box):
        data=box.currentData()
        if data is None:self.proposals.pop(s,None)
        else:self.proposals[s]=data
        self.validate_proposals()

    def proposal_changed(self,s,text):self.proposals[s]=text;self.validate_proposals()

    def _filled(self,widget):
        if isinstance(widget,QComboBox):return widget.isEnabled() and widget.currentData() is not None
        return bool(widget.text().strip())
    def validate_proposals(self):
        error=None
        try:changes,rows=model.plan(self.live_values,self.proposals)
        except (ValueError,KeyError) as exc:changes={};rows=[];error=str(exc)
        for s,(f,e,current) in self.editor_widgets.items():
            filled=self._filled(e)
            e.setProperty('changed',filled);e.setProperty('invalid',bool(error and filled))
            e.style().unpolish(e);e.style().polish(e)
        self.edit_summary.setText(error or (f'{len(rows)} parâmetro(s) proposto(s). Campos vazios serão preservados.' if rows else 'Nenhuma alteração proposta.'))
    def clear_proposals(self):self.proposals={};self.imported_values=None;self.render_editor()

    def check_editor_target(self):
        self.check_bus()
        self.require_selected_controller()
        if self.use_simulation:raise ValueError('Esta operação requer um controlador carregado e o Pico.')
        bus=self.chip()['bus']
        if self.target_address()!=int(bus['pmbus'],16) or self.target_address(self.direct_address)!=int(bus['direct'],16):raise ValueError(f"Use os endereços validados: PMBus {bus['pmbus']} e I²C {bus['direct']}.")

    def accept_board_read(self, result, apply_values):
        """Load a physical read only when every returned register belongs to the selected JSON."""
        if result.get('error') or not result.get('complete'):
            self.live_values = {}
            self.render_editor()
            message = result.get('error') or 'Leitura incompleta. O processo foi interrompido.'
            self.editor_state.setText('Leitura interrompida.')
            QMessageBox.warning(self, 'Leitura interrompida', message)
            return False
        if not result.get('stable'):
            self.editor_state.setText('Leitura instável. Edição bloqueada.')
            return False
        from .config_dump import mismatch_message
        values = {int(key, 16): int(value, 16) for key, value in result['values'].items()}
        message = mismatch_message(values)
        if message:
            self.live_values = {}
            self.render_editor()
            self.editor_state.setText('Leitura interrompida. O CI não corresponde ao JSON selecionado.')
            QMessageBox.warning(self, 'Leitura interrompida', message)
            return False
        apply_values(values)
        return True

    def read_editor(self):
        def start():
            from .config_dump import capture
            from .main import CAPTURES
            self.check_editor_target();self.suspend_monitoring();link=self.link
            self.live_values={};self.render_editor();self.editor_state.setText('Lendo a placa…')
            def done(r):
                self.identity_result=r;self.note(json.dumps(r,ensure_ascii=False))
                def apply_values(values):
                    from .config_dump import format_text
                    self.live_values=values
                    self.dump_view.setPlainText(format_text(self.live_values))
                    self.dump_state.setText('Leitura concluída. Use Salvar leitura para gravar um arquivo.')
                    self.editor_state.setText('Valores atuais lidos da placa • '+r['timestamp_utc']);self.render_editor()
                    if self.imported_values is not None:self.fill_imported()
                self.accept_board_read(r, apply_values)
            self.run(lambda:capture(link,CAPTURES),done)
        self.guard(start)

    def import_editor(self):
        def action():
            from .core import parse_config
            from .config_dump import mask_of
            path,_=QFileDialog.getOpenFileName(self,'Importar propostas de um dump','','Dump (*.txt)')
            if not path:return
            entries=parse_config(Path(path).read_text(encoding='utf-8-sig'))
            if any(e.mask!=mask_of(e.address) for e in entries):raise ValueError('Máscaras incompatíveis com o mapa IR3567B. Importação recusada.')
            self.imported_values={e.address:e.value for e in entries};self.proposals={};self.fill_imported()
            self.tabs.setCurrentWidget(self.parameters_page)
        self.guard(action)

    def fill_imported(self):
        if self.imported_values is None:return
        if not self.live_values:
            self.editor_state.setText('Dump importado. Leia os valores atuais da placa para converter e comparar as propostas.');return
        combined=dict(self.live_values);combined.update(self.imported_values);self.proposals={};used=set()
        # Interpret imports in their own mode; incompatible personalities are not silently translated.
        if 0x14 in self.imported_values and self.imported_values[0x14]!=self.live_values.get(0x14):
            self.editor_state.setText('Modo do dump difere da placa. Propostas não carregadas.');self.render_editor();return
        for f in model.FIELDS:
            if f['address'] not in self.imported_values:continue
            if model.editable(f,self.live_values):
                text=model.proposal_text(f,combined)
                if text and model.code(f,combined)!=model.code(f,self.live_values):
                    if f.get('widget')=='select' and any('code' in choice for choice in f.get('choices',[])):
                        self.proposals[f['symbol']]=model.code(f,combined)
                    else:
                        self.proposals[f['symbol']]=text
                    used.add(f['address'])
        represented={}
        for f in model.FIELDS:
            if f['symbol'] in self.proposals:
                represented[f['address']]=represented.get(f['address'],0)|(((1<<f['length'])-1)<<(8-f['offset']-f['length']))
        other=[a for a,v in self.imported_values.items() if (v^self.live_values.get(a,0))&(~represented.get(a,0)&255)]
        self.editor_state.setText(f'Dump carregado como propostas. {len(other)} registro(s) diferente(s) fora dos campos editáveis não serão aplicados. Revise antes de gravar RAM.')
        self.render_editor()

    def apply_editor(self):
        def start():
            from .param_byte import change_byte
            from .parameters import save_backup
            from .main import CAPTURES
            self.check_editor_target();self.suspend_monitoring()
            if not self.live_values:raise ValueError('Leia os valores atuais primeiro.')
            targets,rows=model.plan(self.live_values,self.proposals)
            if not targets:raise ValueError('Nenhum novo valor diferente foi preenchido.')
            summary='\n'.join(f'{r["group"]} · {r["name"]}: {r["before"]} → {r["after"]}' for r in rows)
            if 0x32 in targets:summary+='\nO limite de desligamento térmico também depende do limite de alerta; confira ambos.'
            if 0x17 in targets or 0x18 in targets:summary+='\nTensão de partida: requer religar as saídas pela aba de manutenção para entrar em vigor.'
            if not confirm(self,'Aplicar em RAM',summary+'\n\nAplicar esses valores? Não consome slot.'):return
            baseline=dict(self.live_values);link=self.link
            def job():
                report=dict(kind='human_parameter_batch',complete=False,rows=rows,results=[],error=None)
                try:
                    # Validate the whole snapshot before the first write, including conversion dependencies.
                    for a in sorted(set(targets) | {extra for extra in (0x14, 0x31, 0x32) if extra in baseline}):
                        live=link.register_read(0x70,a)
                        if not live['pec_verified'] or live['value']!=baseline[a]:raise ValueError('A configuração mudou desde a leitura. Leia novamente antes de aplicar.')
                    report['backup_path']=save_backup(dict(kind='editor_baseline',values=baseline,targets=targets),CAPTURES/'backups')
                    for a,t in sorted(targets.items()):
                        r=change_byte(link,CAPTURES/'backups',a,t,baseline);report['results'].append(r)
                        if not r.get('complete') or r.get('warning'):raise ValueError(r.get('error') or r.get('warning') or 'Aplicação não confirmada')
                    report['complete']=True
                except Exception as exc:report['error']=str(exc)
                report['report_path']=save_backup(report,CAPTURES/'backups');return report
            def done(r):
                self.identity_result=r;self.note(json.dumps(r,ensure_ascii=False));self.imported_values=None
                if r['complete']:
                    self.live_values.update(targets);self.proposals={};self.editor_state.setText('Valores aplicados e verificados em RAM. Gravação permanente ainda não feita.')
                else:
                    self.live_values={};self.editor_state.setText('Aplicação interrompida; pode ser parcial. Leia a placa antes de continuar.')
                    QMessageBox.warning(self,'Aplicação interrompida',r['error'])
                self.render_editor();self.dump_view.clear();self.dump_state.setText('Atualize o dump após alterações em RAM.')
                if r['complete']:self.collect_telemetry(1)
            self.run(job,done)
        self.guard(start)

    def slot_read(self):
        from .slot_commit import user_plan
        r=self.link.register_read(0x70,0xA7)
        if not r['pec_verified']:raise ValueError('Integridade da leitura de slots não confirmada.')
        if (r['value']&15) not in tuple(range(9))+(15,):raise ValueError('Indicador de slots não reconhecido.')
        return user_plan(r['value'])['left']
    def query_slots(self):
        def start():
            self.check_editor_target();self.run(self.slot_read,lambda n:self.slots_label.setText(f'Slots USER disponíveis: {n}'))
        self.guard(start)

    def prepare_commit(self):
        def start():
            from .slot_commit import preview_changes,commit_user_slot
            from .main import CAPTURES
            self.check_editor_target();self.suspend_monitoring()
            if any(isinstance(t,int) or str(t).strip() for t in self.proposals.values()):raise ValueError('Aplique ou limpe os valores antes de gravar permanentemente.')
            link=self.link
            def prepare():return self.slot_read(),preview_changes(link,CAPTURES/'backups')
            def reviewed(data):
                left,r=data;self.slots_label.setText(f'Slots USER disponíveis: {left}');self.identity_result=r
                if left<=0:raise ValueError('Nenhum slot USER disponível.')
                if not r.get('complete') or not r.get('difference_count'):raise ValueError(r.get('error') or 'Nenhuma diferença em relação ao arquivo base; gravação recusada.')
                self.note(json.dumps(r,ensure_ascii=False))
                text=f'A imagem em RAM tem {r["difference_count"]} registro(s) diferente(s) do arquivo base. O relatório de diferenças está no Diagnóstico.\n\nSlots disponíveis agora: {left}\nConsumo: 1 slot USER\nRestarão: {left-1}\n\nA gravação é permanente e interrompe as saídas temporariamente. Confirmar?'
                if not confirm(self,'Confirmar gravação permanente',text):return
                token=r['image_token']
                def commit():
                    if self.slot_read()!=left:raise ValueError('Quantidade de slots mudou; obtenha nova confirmação.')
                    return commit_user_slot(link,CAPTURES/'backups',require='changed',image_token_expected=token)
                def committed(result):
                    self.identity_result=result;self.note(json.dumps(result,ensure_ascii=False))
                    n=result.get('user_left_after');self.slots_label.setText(f'Slots USER disponíveis: {n}' if n is not None else 'Slots USER: consultar novamente')
                    self.live_values={};self.render_editor();self.dump_view.clear();self.dump_state.setText('Leia novamente após a gravação permanente.')
                    msg='Gravação permanente verificada. Leia os valores atuais para continuar.' if result.get('complete') else 'Gravação não confirmada. Não repita automaticamente; consulte o diagnóstico. '+str(result.get('error',''))
                    self.editor_state.setText(msg);QMessageBox.information(self,'Gravação',msg)
                self.run(commit,committed)
            self.run(prepare,reviewed)
        self.guard(start)

    def export_dump(self):
        def action():
            text=self.dump_view.toPlainText()
            if not text:raise ValueError('Leia a placa antes de salvar.')
            path,_=QFileDialog.getSaveFileName(self,'Salvar leitura',datetime.now().strftime('dump_%Y_%m_%d.txt'),'Texto (*.txt)')
            if not path:return
            destination=Path(path)
            if not destination.suffix:destination=destination.with_suffix('.txt')
            destination.write_text(text,encoding='ascii')
            self.dump_state.setText('Leitura salva: '+str(destination))
        self.guard(action)

    def export_monitor(self):
        def action():
            if not self.telemetry_history:raise ValueError('Nenhuma amostra coletada nesta sessão.')
            path,_=QFileDialog.getSaveFileName(self,'Exportar histórico de telemetria','','JSON (*.json)')
            if path:Path(path).write_text(json.dumps(dict(kind='telemetry_history',reports=list(self.telemetry_history),limit=600),ensure_ascii=False,indent=2),encoding='utf-8')
        self.guard(action)

    def start_monitor(self):
        self.monitor_requested=True
        if self.tabs.currentWidget() is self.telemetry_page:
            self.monitoring=True;self.monitor_tick()
        else:
            self.monitoring=False
            self.monitor_state.setText('Monitoramento pronto. Continua quando a aba Telemetria estiver selecionada.')
    def pause_monitoring(self):
        self.monitor_requested=False;self.monitoring=False;self.monitor_timer.stop();self.monitor_state.setText('Monitoramento pausado; amostra em andamento será concluída.')
    def suspend_monitoring(self):
        self.monitoring=False;self.monitor_timer.stop()
        if self.monitor_requested:self.monitor_state.setText('Monitoramento interrompido durante outra operação. Retoma na aba Telemetria.')
    def resume_monitoring_if_needed(self):
        if self.monitor_requested and not self.monitoring and not self.pending and self.tabs.currentWidget() is self.telemetry_page:
            self.monitoring=True
            self.monitor_state.setText('Monitoramento retomado.')
            self.monitor_tick()
    def telemetry_tab_changed(self,index):
        visible=self.tabs.widget(index) is self.telemetry_page
        if visible:
            self.resume_monitoring_if_needed()
        elif self.monitor_requested or self.monitoring:
            self.monitoring=False
            self.monitor_timer.stop()
            if self.monitor_requested:
                self.monitor_state.setText('Monitoramento interrompido fora da aba Telemetria. Retoma ao voltar.')
    def idle_progress(self):
        self.progress.setRange(0,100);self.progress.setValue(0)
    def monitor_tick(self):
        if not self.monitoring:return
        if self.pending:self.monitor_timer.start(200);return
        self.collect_telemetry(1)
    def collect_telemetry(self,cycles):
        def start():
            from .telemetry import collect
            self.check_bus()
            self.require_selected_controller()
            self.cancelled.clear();self.collecting_telemetry=True;self.idle_progress()
            # Keep the last valid reading while the next sample is in flight.
            self.monitor_state.setText('Coletando • '+time.strftime('%H:%M:%S'))
            link=self.link;address=self.target_address();speed=int(self.speed.currentText().split()[0]);sample_base=self.sample_counter
            def done(r):
                self.collecting_telemetry=False;self.idle_progress();self.identity_result=r;self.telemetry_history.append(r);self.sample_counter+=len(r.get('samples',[]))
                seen={reading['command_hex'] for sample in r.get('samples',[]) for reading in sample['readings'] if reading.get('pec_verified') and isinstance(reading.get('value'),(int,float))}
                for key,label in self.metric_labels.items():
                    if key not in seen:
                        label.setStyleSheet('color:#e6af42;');label.setToolTip('Último valor válido; sem nova leitura confirmada nesta coleta.')
                self.select_chart()
                if r.get('error') or r.get('cancelled'):
                    self.pause_monitoring();self.note(str(r.get('error') or 'Coleta cancelada'))
                    if r.get('error'):self.announce_read_failure(r['error'])
                else:
                    self.monitor_state.setText('Última coleta: '+time.strftime('%H:%M:%S')+' • últimas 100 amostras por gráfico')
                    if self.monitoring:self.monitor_timer.start(self.monitor_interval.value()*1000)
            self.run(lambda:collect(link,address,speed,cycles,self.cancelled,lambda row:self.events.put(dict(row,sample=row['sample']+sample_base))),done,True)
        try:start()
        except Exception as exc:self.collecting_telemetry=False;self.pause_monitoring();self.guard(lambda:(_ for _ in ()).throw(exc))
    def update_metric(self,reading):
        c=reading['command_hex'];v=reading.get('value')
        if c in self.graph_data and reading.get('pec_verified') and isinstance(v,(int,float)) and math.isfinite(v):
            points=self.graph_data[c]
            # Position by successful measurements, independently of elapsed time.
            index=points[-1][0]+1 if points else 1
            points.append((index,v));self.metric_labels[c].setText(f'{v:.4g}')
            self.metric_labels[c].setStyleSheet('')
            tip='Leitura confirmada nesta coleta.'
            if c=='8B':tip+=' '+current()['telemetry']['vout']['tooltip']
            self.metric_labels[c].setToolTip(tip)
            self.select_chart()
    def select_chart(self,*_):
        if not hasattr(self,'graph_data'):return
        key,title,unit=METRICS[self.chart_metric.currentIndex()]
        self.plot.points=list(self.graph_data[key]);self.plot.caption=title+' • '+unit;self.plot.update()
    def refresh_phases(self):
        if self.phase_table is None:return
        from . import conversions as conv
        tables=current().get('tables') or {}
        gains=tables.get('phase_gain') or []
        if not gains:
            self.phase_table.setRowCount(0)
            self.phase_state.setText('Este controlador não descreve balanceamento de fases.')
            return
        rows=conv.phase_rows(self.live_values)
        self.phase_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            cells=(f"{gains[i]['address']:02X}",)+tuple(row)
            for j,text in enumerate(cells):
                item=QTableWidgetItem(text)
                if j==0:item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.phase_table.setItem(i,j,item)
        self.phase_state.setText('Aguardando leitura. Use Ler valores atuais ou Ler placa.' if not self.live_values else 'Limites programados da última leitura. Permanecem iguais até nova leitura ou gravação de parâmetros.')
