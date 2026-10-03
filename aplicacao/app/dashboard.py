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

def _import_summary(issues, report):
    lines=[
        f"Ocorrências: {len(issues)}.",
        f"Parâmetros sem regra de validação: {len(report['unvalidated'])}.",
        f"Parâmetros ignorados: {len(report['ignored'])}.",
        f"Registradores com correspondência no JSON: {len(report['imported'])}.",
    ]
    if issues:
        shown=issues[:8]
        lines.append('')
        lines.extend(shown)
        if len(issues)>8:
            lines.append(f"e mais {len(issues)-8}.")
    return '\n'.join(lines)

from .controller_store import current, get, names, selected
class _LiveNames(dict):
    def get(self, key, default=None):
        chip = selected()
        table = get(chip)['telemetry'].get('names') or {} if chip else {}
        return table.get(key, default)
TELEMETRY_NAMES=_LiveNames()

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
        self.edit_origin=None;self.ram_dirty=False
        self.telemetry_metrics=();self.metric_labels={}
        self.monitoring=False;self.monitor_requested=False;self.collecting_telemetry=False;self.sample_counter=0;self.telemetry_history=deque(maxlen=600)
        self.graph_data={}
        self.monitor_timer=QTimer(self);self.monitor_timer.setSingleShot(True);self.monitor_timer.timeout.connect(self.monitor_tick)
        self.tabs.currentChanged.connect(self.telemetry_tab_changed)
        self.rebuild_telemetry_panel();self.render_editor()

    def reset_dashboard(self):
        if not hasattr(self,'live_values'):return
        self.pause_monitoring();self.collecting_telemetry=False;self.sample_counter=0;self.live_values={};self.imported_values=None;self.edit_origin=None;self.ram_dirty=False;self.slots_label.setText('Slots USER: não consultados')
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
                reason=None if isinstance(self.proposals.get(f['symbol']), int) and not model.editable(f, self.live_values) else model.lock_reason(f, self.live_values)
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
        groups=[name for name in [l['label'] for l in chip['loops']]+['Compartilhados'] if name in present]
        groups+=[name for name in present if name not in groups]
        self.loop_tabs.clear();self.editor_tables={}
        for name in groups:
            page=QWidget();layout=QVBoxLayout(page);self.loop_tabs.addTab(page,name)
            self.editor_tables[name]=self.make_editor_table(['Código','Parâmetro','Valor atual','Novo valor','Unidade / validação'],layout)
        page=QWidget();layout=QVBoxLayout(page);self.loop_tabs.addTab(page,'Fases')
        phase_note=QLabel(chip.get('phase_display',{}).get('note','Mapa de fases não descrito neste perfil.'))
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
                if index<0:
                    box.addItem(str(proposal), proposal)
                    index=box.findData(proposal)
                if not can:box.setProperty('imported', True)
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
            box.setEnabled(can or bool(box.property('imported')))
            return box
        proposal=self.proposals.get(f['symbol'])
        view=dict(self.live_values);view.update(getattr(self,'imported_values',None) or {})
        if isinstance(proposal,int):shown=model.import_caption(f,proposal,view)
        elif isinstance(proposal,str):shown=proposal
        else:shown=''
        edit=QLineEdit(shown)
        editable=model.editable(f,self.live_values)
        edit.setReadOnly(not editable)
        if isinstance(proposal,int) and not editable:edit.setProperty('imported',True)
        edit.setPlaceholderText('Manter atual' if editable else '—')
        return edit

    def choice_changed(self,s,box):
        data=box.currentData()
        if data is None:self.proposals.pop(s,None)
        else:self.proposals[s]=data
        self.validate_proposals()

    def proposal_changed(self,s,text):self.proposals[s]=text;self.validate_proposals()

    def _filled(self,widget):
        if isinstance(widget,QComboBox):return widget.currentData() is not None and (widget.isEnabled() or bool(widget.property('imported')))
        return bool(widget.text().strip())
    def validate_proposals(self):
        error=None
        try:changes,rows=model.plan(self.live_values,self.proposals)
        except (ValueError,KeyError) as exc:changes={};rows=[];error=str(exc)
        problems=getattr(self,'import_problems',())
        for s,(f,e,current) in self.editor_widgets.items():
            filled=self._filled(e)
            bad=s in problems
            e.setProperty('changed',bool(filled) and not bad)
            e.setProperty('invalid',bad or bool(error and filled))
            e.style().unpolish(e);e.style().polish(e)
        self.edit_summary.setText(error or (f'{len(rows)} parâmetro(s) proposto(s). Campos vazios serão preservados.' if rows else 'Nenhuma alteração proposta.'))
    def clear_proposals(self):self.proposals={};self.imported_values=None;self.import_problems=set();self.import_notice='';self.render_editor()

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
                    if not self.ram_dirty:self.edit_origin=dict(values)
                    self.dump_view.setPlainText(format_text(self.live_values))
                    self.dump_state.setText('Leitura concluída. Use Salvar leitura para gravar um arquivo.')
                    self.editor_state.setText('Valores atuais lidos da placa • '+r['timestamp_utc']);self.render_editor()
                    if self.imported_values is not None:self.fill_imported()
                self.accept_board_read(r, apply_values)
            self.run(lambda:capture(link,CAPTURES),done)
        self.guard(start)

    def import_editor(self):
        def action():
            from .core import parse_dump_tolerant
            from .config_dump import mask_of
            from PySide6.QtWidgets import QMessageBox
            self.require_selected_controller()
            path,_=QFileDialog.getOpenFileName(self,'Importar propostas de um dump','','Dump (*.txt)')
            if not path:return
            entries,parse_issues=parse_dump_tolerant(Path(path).read_text(encoding='utf-8-sig'))
            report=model.prepare_import(entries,self.live_values,mask_of)
            issues=parse_issues+report['issues']
            if not report['imported']:
                QMessageBox.warning(self,'Importar dump','Nenhum parâmetro do arquivo corresponde ao JSON selecionado. A importação não foi concluída.\n\n'+_import_summary(issues,report))
                return
            if issues or report['unvalidated']:
                text=_import_summary(issues,report)+'\n\nConcluir a importação para gravação posterior? Os valores sem regra de validação ficam sob sua responsabilidade.'
                if not confirm(self,'Importar dump',text):return
            self.imported_values=report['imported']
            self.import_problems=set(report['unvalidated'])
            self.proposals={};self.fill_imported()
            self.tabs.setCurrentWidget(self.parameters_page)
        self.guard(action)

    def fill_imported(self):
        if self.imported_values is None:return
        from .core import Entry
        from .config_dump import mask_of
        entries=[Entry(address,value,mask_of(address)) for address,value in self.imported_values.items()]
        report=model.prepare_import(entries,self.live_values,mask_of)
        self.proposals=report['proposals']
        self.import_problems=set(getattr(self,'import_problems',()) or ())|set(report['unvalidated'])
        text=f"{len(self.proposals)} parâmetro(s) em Novo valor."
        if not self.live_values:text+=' Leia a placa antes de gravar.'
        self.editor_state.setText(text)
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
            if not confirm(self,'Aplicar em RAM',summary+'\n\nAplicar esses valores? Não consome slot.'):return
            baseline=dict(self.live_values);link=self.link;pmbus=int(self.chip()['bus']['pmbus'],16)
            masks={}
            for field in model.FIELDS:
                if field['symbol'] not in self.proposals:continue
                bit=model.field_mask(field)
                if bit:masks[field['address']]=masks.get(field['address'],0)|bit
            write_masks=self.chip()['parameters'].get('write_masks') or {}
            for address in targets:
                masks[address]=int(write_masks.get(str(address),0) or 0)|masks.get(address,0)
            def job():
                report=dict(kind='human_parameter_batch',complete=False,rows=rows,results=[],error=None)
                try:
                    # Validate the whole snapshot before the first write, including conversion dependencies.
                    for a in sorted(set(targets) | {extra for extra in current()['parameters']['snapshot_registers'] if extra in baseline}):
                        live=link.register_read(pmbus,a)
                        if not live['pec_verified'] or live['value']!=baseline[a]:raise ValueError('A configuração mudou desde a leitura. Leia novamente antes de aplicar.')
                    report['backup_path']=save_backup(dict(kind='editor_baseline',values=baseline,targets=targets),CAPTURES/'backups')
                    for a,t in sorted(targets.items()):
                        r=change_byte(link,CAPTURES/'backups',a,t,baseline,masks.get(a));report['results'].append(r)
                        if not r.get('complete') or r.get('warning'):raise ValueError(r.get('error') or r.get('warning') or 'Aplicação não confirmada')
                    report['complete']=True
                except Exception as exc:report['error']=str(exc)
                report['report_path']=save_backup(report,CAPTURES/'backups');return report
            def done(r):
                self.identity_result=r;self.note(json.dumps(r,ensure_ascii=False));self.imported_values=None
                if r['complete']:
                    self.ram_dirty=True;self.live_values.update(targets);self.proposals={}
                    self.editor_state.setText('Valores aplicados e verificados em RAM. Gravar somente parâmetros modificados compara com a leitura anterior a esta alteração, não com o zero que passou a aparecer em Valor atual.')
                else:
                    self.live_values={};self.editor_state.setText('Aplicação interrompida; pode ser parcial. Leia a placa antes de continuar.')
                    QMessageBox.warning(self,'Aplicação interrompida',r['error'])
                self.render_editor();self.dump_view.clear();self.dump_state.setText('Atualize o dump após alterações em RAM.')
                if r['complete']:self.collect_telemetry(1)
            self.run(job,done)
        self.guard(start)

    def slot_read(self):
        from .slot_commit import user_plan
        from .profile_schema import require
        from .registers import identify
        chip = require('slots')
        identify(self.link,int(chip['bus']['pmbus'],16),chip['bus']['speed_khz'])
        mtp = chip.get('mtp')
        if not mtp:
            raise ValueError('O JSON selecionado não descreve os ponteiros de slot.')
        pmbus = int(chip['bus']['pmbus'], 16)
        register = int(mtp['user_pointer_register'])
        r=self.link.register_read(pmbus, register)
        if not r['pec_verified']:raise ValueError('Integridade da leitura de slots não confirmada.')
        nibble = r['value'] & int(mtp['user_pointer_mask'])
        if nibble != int(mtp['user_sentinel']) and nibble >= int(mtp['user_capacity']):
            raise ValueError('Indicador de slots não reconhecido.')
        return user_plan(r['value'])['left']
    def query_slots(self):
        def start():
            self.check_editor_target();self.run(self.slot_read,lambda n:self.slots_label.setText(f'Slots USER disponíveis: {n}'))
        self.guard(start)

    def restore_new_chip(self):
        def action():
            from .core import parse_dump_tolerant
            from .config_dump import capture
            from .main import CAPTURES
            from .profile_schema import require
            from .restore_user import prepare, program, summary
            from .slot_commit import preview_changes, commit_user_slot
            require('commit')
            self.check_editor_target();self.suspend_monitoring()
            path,_=QFileDialog.getOpenFileName(self,'Dump do CI que funcionava','','Dump (*.txt)')
            if not path:return
            entries,parse_issues=parse_dump_tolerant(Path(path).read_text(encoding='utf-8-sig'))
            link=self.link
            def read():
                return capture(link,CAPTURES),self.slot_read()
            def reviewed(data):
                result,left=data
                def keep(values):
                    self.live_values=values
                    if not self.ram_dirty:self.edit_origin=dict(values)
                    self.editor_state.setText('CI novo lido. A cópia ainda não começou.')
                    self.render_editor()
                if not self.accept_board_read(result,keep):return
                self.slots_label.setText(f'Slots USER disponíveis: {left}')
                if left<=0:
                    QMessageBox.warning(self,'Gravar dump completo','Nenhum slot USER disponível. Nada foi copiado.')
                    return
                try:plan=prepare(entries,self.live_values)
                except ValueError as exc:
                    QMessageBox.warning(self,'Gravar dump completo',str(exc));return
                if plan['problems']:
                    QMessageBox.warning(self,'Gravar dump completo','A cópia não começou.\n\n'+'\n'.join(plan['problems']))
                    return
                plan['live']=dict(self.live_values)
                text=summary(plan,self.chip()['id'])
                if parse_issues:text+=f'\n\nO arquivo tem {len(parse_issues)} ocorrência(s) fora dos bytes USER usados.'
                text+=f'\n\nSlots disponíveis agora: {left}. Será consumido 1.'
                if not confirm(self,'Gravar dump completo',text):return
                origin=dict(self.live_values);image=dict(plan['image'])
                def job():
                    try:
                        report=program(link,plan)
                        if not report['ok']:return dict(phase='ram',complete=False,error=(report.get('error') or 'Cópia interrompida')+' O slot não foi gravado.',written=report['written'])
                        after=capture(link,CAPTURES)
                        if not after.get('stable') or not after.get('values'):
                            return dict(phase='verify',complete=False,error='A leitura depois da cópia não ficou estável. O slot não foi gravado.')
                        got={int(key,16):int(value,16) for key,value in after['values'].items()}
                        differ=[address for address,value in image.items() if got.get(address)!=value]
                        if differ:return dict(phase='verify',complete=False,error='A RAM não ficou igual ao arquivo. O slot não foi gravado. '+', '.join(f'{a:02X}' for a in differ[:12]))
                        if self.slot_read()!=left:return dict(phase='slot',complete=False,error='A quantidade de slots mudou. O slot não foi gravado.')
                        mode='changed' if plan['writes'] else 'match'
                        baseline=origin if mode=='changed' else got
                        preview=preview_changes(link,CAPTURES/'backups',baseline=baseline)
                        if not preview.get('complete'):return dict(phase='preview',complete=False,error=preview.get('error') or 'Prévia não confirmada. O slot não foi gravado.')
                        if mode=='changed' and not preview.get('difference_count'):
                            return dict(phase='preview',complete=False,error='A RAM não mostra a diferença copiada. O slot não foi gravado.')
                        if self.slot_read()!=left:return dict(phase='slot',complete=False,error='A quantidade de slots mudou. O slot não foi gravado.')
                        result=commit_user_slot(link,CAPTURES/'backups',require=mode,image_token_expected=preview['image_token'],baseline=baseline)
                        result['phase']='commit';return result
                    except Exception as exc:
                        return dict(phase='ram',complete=False,error=str(exc)+' O slot não foi gravado.')
                def finished(result):
                    self.identity_result=result;self.note(json.dumps(result,ensure_ascii=False))
                    self.live_values={};self.edit_origin=None;self.ram_dirty=False;self.imported_values=None;self.proposals={};self.render_editor();self.dump_view.clear()
                    if result.get('complete'):
                        n=result.get('user_left_after');self.slots_label.setText(f'Slots USER disponíveis: {n}' if n is not None else 'Slots USER: consultar novamente')
                        msg='Imagem USER gravada e conferida depois da recarga. Leia os valores atuais. O trim e a área de fabricante continuam os deste CI.'
                    else:
                        msg='A restauração não foi concluída. Não repita automaticamente. '+str(result.get('error') or 'Falha sem detalhe.')
                    self.editor_state.setText(msg);self.dump_state.setText('Leia novamente após a restauração.');QMessageBox.information(self,'Gravar dump completo',msg)
                self.run(job,finished)
            self.run(read,reviewed)
        self.guard(action)

    def prepare_commit(self):
        def start():
            from .profile_schema import require
            require('commit')
            from .slot_commit import preview_changes,commit_user_slot
            from .main import CAPTURES
            self.check_editor_target();self.suspend_monitoring()
            if not self.edit_origin:raise ValueError('Leia os valores atuais antes de gravar somente os parâmetros modificados.')
            if any(isinstance(t,int) or str(t).strip() for t in self.proposals.values()):raise ValueError('Aplique ou limpe os valores antes de gravar somente os parâmetros modificados.')
            link=self.link;origin=dict(self.edit_origin)
            def prepare():return self.slot_read(),preview_changes(link,CAPTURES/'backups',baseline=origin)
            def reviewed(data):
                left,r=data;self.slots_label.setText(f'Slots USER disponíveis: {left}');self.identity_result=r
                if left<=0:raise ValueError('Nenhum slot USER disponível.')
                if not r.get('complete') or not r.get('difference_count'):raise ValueError(r.get('error') or 'A RAM está igual à leitura anterior à alteração. Não há diferença nova para gravar em definitivo.')
                self.note(json.dumps(r,ensure_ascii=False))
                text=self.chip().get('validation',{}).get('notice','')+'\n\n'+f'A imagem em RAM tem {r["difference_count"]} registro(s) diferente(s) da leitura feita antes da alteração. O campo Valor atual pode já mostrar o valor novo; a comparação não usa esse campo.\n\nSlots disponíveis agora: {left}\nConsumo: 1 slot USER\nRestarão: {left-1}\n\nA gravação é permanente e interrompe as saídas temporariamente. Confirmar?'
                if not confirm(self,'Gravar somente parâmetros modificados',text):return
                token=r['image_token']
                def commit():
                    if self.slot_read()!=left:raise ValueError('Quantidade de slots mudou; obtenha nova confirmação.')
                    return commit_user_slot(link,CAPTURES/'backups',require='changed',image_token_expected=token,baseline=origin)
                def committed(result):
                    self.identity_result=result;self.note(json.dumps(result,ensure_ascii=False))
                    n=result.get('user_left_after');self.slots_label.setText(f'Slots USER disponíveis: {n}' if n is not None else 'Slots USER: consultar novamente')
                    self.live_values={};self.edit_origin=None;self.ram_dirty=False;self.render_editor();self.dump_view.clear();self.dump_state.setText('Leia novamente após gravar os parâmetros modificados.')
                    msg='Parâmetros modificados gravados e conferidos. Leia os valores atuais para continuar.' if result.get('complete') else 'Gravação não confirmada. Não repita automaticamente; consulte o diagnóstico. '+str(result.get('error',''))
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
            if c==f"{(current().get('telemetry') or {}).get('vout',{}).get('command',-1):02X}":tip+=' '+current()['telemetry']['vout'].get('tooltip','')
            self.metric_labels[c].setToolTip(tip)
            self.select_chart()
    def select_chart(self,*_):
        if not hasattr(self,'graph_data'):return
        metrics=getattr(self,'telemetry_metrics',())
        index=self.chart_metric.currentIndex() if hasattr(self,'chart_metric') else -1
        if not metrics or index<0 or index>=len(metrics):
            self.plot.points=[];self.plot.caption='';self.plot.update();return
        key,title,unit=metrics[index]
        self.plot.points=list(self.graph_data[key]);self.plot.caption=title+' • '+unit;self.plot.update()
    def rebuild_telemetry_panel(self):
        from PySide6.QtWidgets import QGroupBox,QLabel,QVBoxLayout
        chip=get(self.profile.currentText()) if self.profile.currentText() in names() else None
        tele=(chip or {}).get('telemetry') or {}
        metrics=tuple((item['key'],item['title'],item['unit']) for item in tele.get('metrics') or [])
        grid_spec=tuple(tuple(item) for item in tele.get('metric_grid') or [])
        self.telemetry_metrics=metrics
        layout=self.metric_grid
        while layout.count():
            item=layout.takeAt(0)
            widget=item.widget()
            if widget is not None:widget.deleteLater()
        self.metric_labels={}
        vout=tele.get('vout') or {}
        vout_key=f"{vout['command']:02X}" if 'command' in vout else ''
        for row_index,column,key in grid_spec:
            title,unit=next((item[1],item[2]) for item in metrics if item[0]==key)
            box=QGroupBox(title+' • '+unit);box.setObjectName('metricbox');col=QVBoxLayout(box);col.setContentsMargins(6,4,6,2)
            label=QLabel('—');label.setObjectName('metric');col.addWidget(label);layout.addWidget(box,row_index,column)
            self.metric_labels[key]=label
            if key==vout_key and vout.get('tooltip'):label.setToolTip(vout['tooltip'])
        self.graph_data={key:deque(maxlen=100) for key,_,_ in metrics}
        self.chart_metric.blockSignals(True)
        self.chart_metric.clear()
        titles=[title for _,title,_ in metrics]
        self.chart_metric.addItems(titles)
        text_width=max((self.chart_metric.fontMetrics().horizontalAdvance(title) for title in titles), default=0)
        self.chart_metric.setMinimumWidth(text_width+56)
        self.chart_metric.view().setMinimumWidth(text_width+24)
        self.chart_metric.blockSignals(False)
        self.select_chart()
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
