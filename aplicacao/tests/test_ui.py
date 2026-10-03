import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from app.main import Window

class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application=QApplication.instance() or QApplication([])

    def setUp(self):
        ports=[dict(device='COM1',description='Serial',vid=None,pid=None,serial=''),
               dict(device='COM7',description='Pico',vid=0x2E8A,pid=10,serial='test')]
        with patch('app.main.serial_ports',return_value=ports),patch('app.main.Pico') as hardware:
            self.w=Window()
            hardware.assert_not_called()

    def tearDown(self):self.w.close()

    def test_defaults_do_not_open_hardware(self):
        w=self.w
        self.assertFalse(hasattr(w,'mode'))
        self.assertEqual(w.profile.currentText(),'Selecione o CI')
        self.assertEqual(w.profile.itemText(0),'Selecione o CI')
        self.assertGreaterEqual(w.profile.count(),2)
        self.assertIn('IR3567B',[w.profile.itemText(i) for i in range(w.profile.count())])
        self.assertEqual(w.loop_tabs.count(),0)
        self.assertFalse(w.editor_widgets)
        self.assertEqual(w.port.currentData(),'COM7')
        self.assertEqual(w.port.currentText(),'COM7 — Dispositivo Serial USB (COM7)')
        self.assertEqual(w.port.minimumWidth(),w.port.maximumWidth())
        self.assertLess(w.port.maximumWidth(),480)
        self.assertIsNone(w.link)
        self.assertIsNone(w.pending)
        self.assertFalse(w.bus_ready.isChecked())
        self.assertFalse(w.param_confirm.isChecked())
        self.assertFalse(w.reen_confirm.isChecked())
        self.assertFalse(w.windowIcon().isNull())

    def test_unchecked_bus_names_the_checkbox(self):
        w=self.w;w.link=object();w.bus_ready.setChecked(False)
        with self.assertRaises(ValueError) as caught:w.check_bus()
        self.assertIn('Marque o checkbox «Barramento conferido: 3,3 V • GND comum • nenhum outro mestre ativo»',str(caught.exception))
        w.link=None
    def test_unresponsive_board_keeps_the_pico_and_asks_for_power(self):
        from concurrent.futures import Future
        from unittest.mock import Mock
        w=self.w;link=Mock();link.drain_trace.return_value=[];w.link=link
        future=Future();future.set_exception(ValueError('Não foi possível confirmar resposta do CI. Verifique alimentação da placa, GND comum e SDA/SCL.'))
        w.pending=(future,Mock())
        with patch('app.main.QMessageBox.warning') as box:
            w.poll()
        self.assertIs(w.link,link);link.close.assert_not_called()
        self.assertIn('Confirme se a placa está energizada',box.call_args.args[2])
    def test_slow_job_shows_wait_cursor_until_finished(self):
        from concurrent.futures import Future
        from PySide6.QtCore import Qt
        w=self.w
        future=Future();future.set_result('ok');w.pool.submit=lambda fn:future
        during=[]
        try:
            w.run(lambda:None,lambda result:during.append(QApplication.overrideCursor()))
            self.assertEqual(QApplication.overrideCursor().shape(),Qt.WaitCursor)
            w.poll()
            self.assertIsNone(during[0])
            self.assertIsNone(QApplication.overrideCursor())
            self.assertFalse(w.wait_cursor)
        finally:
            w.pending=None;w.end_wait_cursor()
    def test_monitoring_sample_keeps_the_normal_cursor(self):
        from concurrent.futures import Future
        w=self.w;w.monitoring=True;w.collecting_telemetry=True
        future=Future();future.set_result('ok');w.pool.submit=lambda fn:future
        w.run(lambda:None,lambda result:None)
        self.assertIsNone(QApplication.overrideCursor())
        w.poll()
    def test_addresses_are_independent(self):
        w=self.w
        self.assertEqual(w.target_address(),0x70)
        self.assertEqual(w.target_address(w.direct_address),8)
        w.direct_address.setText('09')
        self.assertEqual(w.target_address(),0x70)
        self.assertEqual(w.address.text(),'70')

    def test_graph_keeps_latest_100_samples(self):
        for i in range(125):self.w.update_metric(dict(command_hex='8B',value=i,pec_verified=True))
        points=list(self.w.graph_data['8B'])
        self.assertEqual(len(points),100);self.assertEqual(points[0],(26,25));self.assertEqual(points[-1],(125,124))
        self.assertEqual(self.w.metric_labels['8B'].text(),'124')
        self.w.update_metric(dict(command_hex='8B',status='unsupported'))
        self.assertEqual(self.w.metric_labels['8B'].text(),'124')

    def test_dump_read_does_not_ask_to_save(self):
        from unittest.mock import Mock
        w=self.w;w.check_editor_target=Mock();w.run=Mock()
        with patch('app.dashboard.QFileDialog.getSaveFileName') as dialog:
            w.read_editor();dialog.assert_not_called();w.run.assert_called_once()
    def test_save_reading_suggests_dated_name(self):
        w=self.w;w.dump_view.setPlainText('10 00 FF\r\n')
        with patch('app.dashboard.QFileDialog.getSaveFileName',return_value=('','')) as dialog:
            w.export_dump()
            self.assertRegex(dialog.call_args.args[2],r'dump_\d{4}_\d{2}_\d{2}\.txt')

    def test_current_read_only_and_blank_new_values(self):
        w=self.w;w.profile.setCurrentText('IR3567B');w.live_values={0x14:0x22,0x26:255};w.render_editor()
        from PySide6.QtWidgets import QComboBox
        _,new,current=w.editor_widgets['LOOP_1_VID_OFFSET']
        self.assertTrue(current.isReadOnly());self.assertIsInstance(new,QComboBox)
        self.assertEqual(new.currentText(),'Manter atual');self.assertEqual(current.text(),'0 mV')
        new.setCurrentIndex(new.findData(14));self.assertTrue(new.property('changed'))
        w.invalidate();self.assertFalse(w.live_values);self.assertFalse(w.proposals)

    def test_import_is_proposal_only_and_preserves_live_values(self):
        w=self.w;w.live_values={0x14:0x22,0x26:255};w.imported_values={0x26:239}
        w.fill_imported()
        self.assertEqual(w.live_values[0x26],255)
        self.assertEqual(w.proposals['LOOP_1_VID_OFFSET'],14)
        self.assertIsNone(w.pending);self.assertIsNone(w.link)

    def test_declining_permanent_confirmation_never_commits(self):
        from unittest.mock import Mock
        w=self.w;w.check_editor_target=Mock();w.slot_read=Mock(return_value=6)
        w.run=lambda fn,done,**kw:done(fn())
        with patch('app.slot_commit.preview_changes',return_value=dict(complete=True,difference_count=1,image_token='test')):
            with patch('app.slot_commit.commit_user_slot') as commit,patch('app.dashboard.confirm',return_value=False) as question:
                w.prepare_commit();commit.assert_not_called()
                message=question.call_args.args[2]
                self.assertIn('Slots disponíveis agora: 6',message);self.assertIn('Restarão: 5',message)

    def test_only_current_tabs_are_visible(self):
        titles=[self.w.tabs.tabText(i) for i in range(self.w.tabs.count())]
        self.assertEqual(titles,['Telemetria','Dump','Parâmetros e gravação','Diagnóstico e manutenção'])
        self.assertFalse(hasattr(self.w,'telemetry_tabs'))
        self.w.profile.setCurrentText('IR3567B')
        self.assertEqual([self.w.loop_tabs.tabText(i) for i in range(self.w.loop_tabs.count())],['Loop 1','Loop 2','Compartilhados','Fases'])
        layout=self.w.plot.parentWidget().layout()
        self.assertGreater(layout.stretch(layout.indexOf(self.w.plot)),layout.stretch(layout.indexOf(self.w.telemetry_table)))
        self.assertEqual(set(self.w.graph_data),{'8B','8D','8C','96','88','89','8E','97'})
        self.assertFalse(any(b.text()=='VRM  /  BENCH' for b in self.w.findChildren(type(self.w.status))))
        self.assertEqual(self.w.phase_table.item(0,0).text(),'1E')
        self.assertEqual(self.w.phase_table.item(0,2).text(),'Aguardando leitura')
        self.w.resize(1280,900);self.w.show();self.application.processEvents()
        from PySide6.QtCore import QPoint
        def origin(key):return self.w.metric_labels[key].mapTo(self.w,QPoint(0,0))
        for above,below in (('88','8B'),('89','8C'),('8D','8E'),('97','96')):
            self.assertLess(origin(above).y(),origin(below).y())
            self.assertAlmostEqual(origin(above).x(),origin(below).x(),delta=12)
        self.assertFalse(self.w.reload_confirm.isChecked())
        self.assertFalse(self.w.commit_confirm.isChecked())
        self.assertFalse(self.w.live_values)
        self.assertFalse(self.w.monitoring)
        self.assertFalse(hasattr(self.w,'preset'))
    def test_closed_list_uses_a_selector_and_keeps_the_code(self):
        from PySide6.QtWidgets import QComboBox,QLineEdit
        w=self.w
        w.profile.setCurrentText('IR3567B')
        w.live_values={0x14:0x22,0x32:0,0x24:40}
        w.render_editor()
        ocp=w.editor_widgets['OCP_MODE'][1]
        loops=w.editor_widgets['LOOPS_CONFIGURATION'][1]
        load=w.editor_widgets['LOOP_1_LL_REG'][1]
        self.assertIsInstance(ocp,QComboBox)
        self.assertTrue(ocp.isEnabled())
        self.assertEqual(ocp.itemText(1),'Desliga imediatamente')
        self.assertEqual(ocp.itemData(1),0)
        ocp.setCurrentIndex(3)
        self.assertEqual(w.proposals['OCP_MODE'],2)
        self.assertIsInstance(loops,QComboBox)
        self.assertFalse(loops.isEnabled())
        self.assertEqual(loops.currentText(),'6 + 0 fases')
        self.assertIsInstance(load,QLineEdit)
        codes=[w.editor_tables['Compartilhados'].item(i,0).text() for i in range(w.editor_tables['Compartilhados'].rowCount())]
        self.assertIn('32',codes)
        loop1=w.editor_tables['Loop 1']
        vid=next(i for i in range(loop1.rowCount()) if loop1.item(i,1).text()=='Ajuste de tensão')
        self.assertEqual(loop1.item(vid,0).text(),'26')
        self.assertEqual(w.editor_tables['Loop 1'].horizontalHeaderItem(0).text(),'Código')

    def test_monitor_follows_the_telemetry_tab(self):
        w=self.w;w.collect_telemetry=lambda cycles:None
        w.tabs.setCurrentWidget(w.telemetry_page)
        w.start_monitor()
        self.assertTrue(w.monitoring);self.assertTrue(w.monitor_requested)
        w.tabs.setCurrentIndex(1)
        self.assertFalse(w.monitoring);self.assertTrue(w.monitor_requested);self.assertFalse(w.monitor_timer.isActive())
        w.tabs.setCurrentWidget(w.telemetry_page)
        self.assertTrue(w.monitoring)
        w.suspend_monitoring()
        self.assertFalse(w.monitoring);self.assertTrue(w.monitor_requested)
        w.tabs.setCurrentIndex(1);w.tabs.setCurrentWidget(w.telemetry_page)
        self.assertTrue(w.monitoring)
        w.pause_monitoring()
        self.assertFalse(w.monitor_requested)
        w.tabs.setCurrentIndex(1);w.tabs.setCurrentWidget(w.telemetry_page)
        self.assertFalse(w.monitoring)
    def test_telemetry_samples_do_not_fill_the_progress_bar(self):
        w=self.w;w.progress.setValue(10)
        w.events.put(dict(sample=1,command_hex='8B',name='READ_VOUT',raw_hex='021D',display='1.056 V',pec_verified=True,value=1.056))
        w.poll()
        self.assertEqual(w.progress.value(),10)
        labels={b.text() for b in self.w.findChildren(type(self.w.stop))}
        self.assertIn('Ler placa',labels);self.assertIn('Salvar leitura',labels)
        self.assertIn('Limpar valores',labels);self.assertIn('Limpar log',labels)
        self.assertIn('Desligar e religar saídas',labels);self.assertIn('Recarregar memória permanente',labels)
        self.assertNotIn('Importar para parâmetros…',labels)
        self.assertFalse(self.w.address.parentWidget().isVisible())
        self.w.log.setPlainText('registro')
        next(b for b in self.w.findChildren(type(self.w.stop)) if b.text()=='Limpar log').click()
        self.assertEqual(self.w.log.toPlainText(),'')

    def test_placeholder_asks_for_a_controller_before_board_reads(self):
        w=self.w;w.link=object();w.bus_ready.setChecked(True)
        with patch('app.main.QMessageBox.warning') as box:
            w.read_editor()
        self.assertIn('Selecione o CI correto',box.call_args.args[2])
        with patch('app.main.QMessageBox.warning') as box:
            w.start_telemetry(1)
        self.assertIn('Selecione o CI correto',box.call_args.args[2])
        self.assertFalse(w.monitoring)
        w.link=None

    def test_code_is_centered_and_locked_fields_explain_themselves(self):
        from PySide6.QtCore import Qt
        w=self.w
        w.profile.setCurrentText('IR3567B')
        self.assertTrue(w.phase_table.item(0,0).textAlignment() & Qt.AlignmentFlag.AlignHCenter)
        self.assertTrue(w.editor_tables['Loop 1'].horizontalHeaderItem(0).textAlignment() & Qt.AlignmentFlag.AlignHCenter)
        w.live_values={0x14:0x22,0x61:0}
        w.render_editor()
        shared=w.editor_tables['Compartilhados']
        row=next(i for i in range(shared.rowCount()) if shared.item(i,1).text()=='Modo de aplicação')
        self.assertIn('61',shared.item(row,4).text())
        self.assertFalse(w.editor_widgets['APPLICATION_MODE'][1].isEnabled())
        self.assertIn('14',w.editor_widgets['SEQUENCE_MODE'][1].toolTip())

    def test_controller_change_stops_work_and_loads_the_new_json(self):
        from concurrent.futures import Future
        from unittest.mock import Mock
        from app import controller_store
        w=self.w
        w.monitor_requested=True;w.monitoring=True;w.proposals={'OCP_MODE':2};w.live_values={0x32:1}
        done=Mock();future=Future();future.set_result({'samples':[]})
        w.pending=(future,done,w.work_generation)
        demo={'id':'ZZDEMO','bus':{'pmbus':'71','direct':'09','register':'0D'},'parameters':{'blocked':[]},
              'tables':{'phase_count':{'address':20,'offset':3,'length':5},'phase_gain':[],'loop1_phases':[0]*32,'loop2_phases':[0]*32},
              'fields':[{'symbol':'DEMO_FLAG','label':'Sinal do novo CI','group':'Especial','address':16,'offset':0,'length':1,
                         'unit':'','hint':'bit','description':'Campo do JSON novo','widget':'text',
                         'conversion':{'type':'enum','editable':True,'options':[{'code':0,'text':'Não'},{'code':1,'text':'Sim'}]}}]}
        controller_store._chips['ZZDEMO']=demo
        try:
            w.profile.addItem('ZZDEMO');w.profile.setCurrentText('ZZDEMO');w.poll()
            done.assert_not_called()
            self.assertIsNone(w.pending)
            self.assertFalse(w.monitor_requested);self.assertFalse(w.monitoring);self.assertFalse(w.proposals)
            self.assertEqual(w.address.text(),'71')
            self.assertEqual([w.loop_tabs.tabText(i) for i in range(w.loop_tabs.count())],['Especial','Fases'])
            self.assertEqual(w.editor_tables['Especial'].item(0,1).text(),'Sinal do novo CI')
            self.assertEqual(w.editor_tables['Especial'].item(0,0).text(),'10')
        finally:
            controller_store._chips.pop('ZZDEMO',None)
            controller_store.select('IR3567B')

    def test_foreign_read_alerts_and_does_not_load(self):
        from app import controller_store
        w=self.w
        w.profile.setCurrentText('IR35217')
        foreign=dict(complete=True, stable=True, error=None, values={'01': '00'}, timestamp_utc='t')
        try:
            with patch('app.main.QMessageBox.warning') as box:
                self.assertFalse(w.accept_board_read(foreign, lambda values: self.fail(values)))
            self.assertIn('não estão no JSON', box.call_args.args[2])
            self.assertEqual(w.live_values, {})
            self.assertIn('interrompida', w.editor_state.text())
        finally:
            controller_store.select('IR3567B')
