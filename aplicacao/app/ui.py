from PySide6.QtCore import Qt
from PySide6.QtWidgets import *
from .dashboard import TrendPlot

STYLE='''
QWidget {background:#0c1423;color:#dfe8f4;font-family:Segoe UI;font-size:10pt;}
QGroupBox {border:1px solid #29374b;border-radius:8px;margin-top:12px;padding:14px 10px 8px;}
QGroupBox::title {subcontrol-origin:margin;left:12px;color:#8fa7c6;}
QLineEdit,QComboBox,QSpinBox,QPlainTextEdit {background:#131f32;border:1px solid #34465e;border-radius:5px;padding:6px;}
QLineEdit:read-only {color:#9eb5cc;background:#0f1b2c;}
QLineEdit[changed="true"],QComboBox[changed="true"] {background:#382d15;border:1px solid #e6af42;color:#ffe2a0;}
QLineEdit[invalid="true"],QComboBox[invalid="true"] {background:#3d202b;border:1px solid #ec7189;color:#f6d5dc;}
QLineEdit:read-only[invalid="true"],QComboBox:disabled[invalid="true"] {background:#3d202b;border:1px solid #ec7189;color:#f6d5dc;}
QComboBox:disabled {color:#9eb5cc;}
QPushButton {background:#20334d;border:1px solid #3a526f;border-radius:6px;padding:8px 12px;}
QPushButton:hover {background:#2c496b;} QPushButton:disabled {color:#68778e;background:#142034;}
QPushButton[primary="true"] {background:#106b86;border-color:#26b5ce;color:white;}
QTabWidget::pane {border:1px solid #29374b;} QTabBar::tab {background:#111d30;padding:10px 16px;color:#92a8c3;}
QTabBar::tab:selected {background:#21344f;color:#66d9ec;border-bottom:2px solid #35c1da;}
QTableWidget {background:#101b2d;alternate-background-color:#142238;border:0;gridline-color:#243249;}
QHeaderView::section {background:#1e3048;color:#a9bed8;padding:8px;border:0;}
QProgressBar {background:#14243b;text-align:center;} QProgressBar::chunk {background:#168ba4;}
QGroupBox#metricbox {margin-top:8px;padding:2px 6px 2px;}
QGroupBox#metricbox::title {font-size:8pt;}
QLabel#metric {font-size:13pt;color:#6bd9eb;}
QLabel#muted {color:#91a9c5;}
'''

def build_ui(w):
    w.setStyleSheet(STYLE);w.controls=[]
    root=QWidget();w.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(18,12,18,12);layout.setSpacing(10)
    w.status=QLabel('Desconectado • selecione a porta e conecte');layout.addWidget(w.status)
    def field(name,widget):setattr(w,name,widget);w.controls.append(widget);return widget
    def combo(name,items):
        c=field(name,QComboBox());c.addItems(items);return c
    def row(parent):r=QHBoxLayout();parent.addLayout(r);return r
    def button(r,text,fn,primary=False):
        b=w.button(r,text,fn);b.setProperty('primary',primary);return b
    def note(g,text):
        l=QLabel(text);l.setWordWrap(True);l.setObjectName('muted');g.addWidget(l);return l
    connection=QGroupBox('Conexão com Raspberry Pi Pico');layout.addWidget(connection);grid=QGridLayout(connection)
    from .controller_store import names, selected, get
    chip=get(selected()) if selected() else None
    grid.addWidget(QLabel('Controlador'),0,0);grid.addWidget(combo('profile',['Selecione o CI']+names()),1,0)
    grid.addWidget(QLabel('Porta serial'),0,1);grid.addWidget(combo('port',[]),1,1)
    w.port.setEditable(True)
    w.profile.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    w.port.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
    actions=QHBoxLayout();grid.addLayout(actions,1,2)
    for title,fn in [('Atualizar',w.refresh_ports),('Identificar',w.identify_picos),('Conectar',w.connect),('Desconectar',w.invalidate)]:button(actions,title,fn)
    grid.setColumnStretch(3,1)
    grid.addWidget(field('bus_ready',QCheckBox('Barramento conferido: 3,3 V • GND comum • nenhum outro mestre ativo')),2,0,1,4)
    w.tabs=QTabWidget();layout.addWidget(w.tabs,1)
    def tab(title):
        p=QWidget();g=QVBoxLayout(p);g.setContentsMargins(16,14,16,14);g.setSpacing(10);w.tabs.addTab(p,title);return p,g
    def table(headers,g):
        t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.setAlternatingRowColors(True)
        t.setEditTriggers(QTableWidget.NoEditTriggers);t.verticalHeader().hide();t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);g.addWidget(t,1);return t
    w.telemetry_page,g=tab('Telemetria')
    note(g,'Saída atualmente endereçada. A associação ao loop/VCORE depende da placa; não há troca automática de loop. Escalas a confirmar com medição externa.')
    r=row(g);button(r,'Ler agora',lambda:w.start_telemetry(1),True);r.addWidget(QLabel('Intervalo entre coletas (s)'))
    w.monitor_interval=field('monitor_interval',QSpinBox());w.monitor_interval.setRange(1,60);w.monitor_interval.setValue(2);r.addWidget(w.monitor_interval)
    button(r,'Iniciar monitoramento',w.start_monitor);w.pause_monitor=QPushButton('Pausar');r.addWidget(w.pause_monitor);w.pause_monitor.clicked.connect(w.pause_monitoring);button(r,'Exportar histórico',w.export_monitor);r.addStretch()
    w.monitor_state=note(g,'Monitoramento parado. Nenhuma leitura automática ao conectar.')
    w.metric_labels={};w.metric_grid=QGridLayout();w.metric_grid.setHorizontalSpacing(8);w.metric_grid.setVerticalSpacing(4);g.addLayout(w.metric_grid)
    r=row(g);r.addWidget(QLabel('Gráfico'));w.chart_metric=QComboBox()
    w.chart_metric.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    w.chart_metric.view().setTextElideMode(Qt.TextElideMode.ElideNone)
    r.addWidget(w.chart_metric);r.addStretch()
    w.plot=TrendPlot();w.plot.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);g.addWidget(w.plot,2);w.chart_metric.currentIndexChanged.connect(w.select_chart)
    w.telemetry_table=table(['Amostra','Medição','Detalhe técnico','Valor / estado','Integridade'],g)
    w.telemetry_table.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored)
    _,g=tab('Dump')
    note(g,'Mapa utilizado: parâmetros e máscaras em três colunas. Duas leituras conferem estabilidade. O TXT mantém o formato hexadecimal de intercâmbio.')
    r=row(g);button(r,'Ler placa',w.read_editor,True);button(r,'Salvar leitura',w.export_dump)
    w.dump_view=QPlainTextEdit();w.dump_view.setReadOnly(True);g.addWidget(w.dump_view,1);w.dump_state=note(g,'Nenhum dump capturado nesta sessão.')
    w.parameters_page,g=tab('Parâmetros e gravação')
    r=row(g);button(r,'Ler valores atuais',w.read_editor,True);button(r,'Importar dump…',w.import_editor);button(r,'Limpar valores',w.clear_proposals);r.addStretch()
    w.editor_state=note(g,'Selecione o CI para carregar os parâmetros.')
    note(g,'Atual = última leitura, somente leitura. Em lista fechada, Novo é uma seleção: o texto descreve e o código é gravado. Manter atual preserva o parâmetro. Amarelo indica proposta; vermelho indica valor inválido. Quando Novo valor fica fechado, a coluna Unidade / validação explica o motivo.')
    w.loop_tabs=QTabWidget();g.addWidget(w.loop_tabs,1);w.editor_tables={};w.phase_table=None
    w.edit_summary=note(g,'Nenhuma alteração proposta.')
    r=row(g);button(r,'Aplicar novos valores em RAM',w.apply_editor,True);r.addStretch()
    w.slots_label=QLabel('Slots USER: não consultados');r.addWidget(w.slots_label);button(r,'Consultar slots',w.query_slots)
    r=row(g);button(r,'Gravar dump completo',w.restore_new_chip,True);button(r,'Gravar somente parâmetros modificados',w.prepare_commit)
    note(g,'Gravar dump completo copia a área USER do arquivo para este CI e grava um slot. O trim e a área de fabricante deste CI permanecem os dele. Gravar somente parâmetros modificados grava só o que já foi alterado e aplicado em RAM.')
    _,g=tab('Diagnóstico e manutenção')
    settings=QGroupBox('Endereços avançados');settings.setVisible(False);g.addWidget(settings);f=QGridLayout(settings)
    bus=chip['bus'] if chip else {}
    for i,(title,name,value) in enumerate([('PMBus (hexadecimal)','address',bus.get('pmbus','')),('I²C direto (hexadecimal)','direct_address',bus.get('direct',''))]):
        f.addWidget(QLabel(title),0,i);f.addWidget(field(name,QLineEdit(value)),1,i)
    f.addWidget(QLabel('Velocidade'),0,2);f.addWidget(combo('speed',['100 kHz','50 kHz','10 kHz']),1,2)
    note(g,'Manutenção usa as receitas do JSON selecionado. Recursos não descritos são recusados antes de escrever.')
    g.addWidget(field('reen_confirm',QCheckBox('Autorizo desligar e religar as saídas para aplicar a configuração de partida.')))
    r=row(g);button(r,'Desligar e religar saídas',w.start_reenable)
    g.addWidget(field('reload_confirm',QCheckBox('Autorizo recarregar os valores permanentes, substituindo a configuração em RAM.')))
    r=row(g);button(r,'Recarregar memória permanente',w.start_reload)
    r=row(g);button(r,'Limpar log',lambda:w.log.clear());r.addStretch()
    w.log=QPlainTextEdit();w.log.setReadOnly(True);w.log.document().setMaximumBlockCount(3000);g.addWidget(w.log,1)
    w.param_log=w.reload_log=w.commit_log=w.dump_log=w.mtp_log=w.log
    r=row(layout);button(r,'Exportar resultado',w.export);button(r,'Salvar log',w.save_log);r.addStretch()
    w.stop=QPushButton('Cancelar leitura');w.stop.setEnabled(False);w.stop.clicked.connect(w.cancelled.set);r.addWidget(w.stop)
    w.progress=QProgressBar();w.progress.setRange(0,100);w.progress.setMaximumWidth(220);r.addWidget(w.progress)
    w.param_register=QComboBox();w.param_value=QLineEdit();w.param_confirm=QCheckBox();w.commit_confirm=QCheckBox()
    w.init_dashboard()
