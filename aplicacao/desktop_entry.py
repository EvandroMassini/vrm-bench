import sys
import traceback
from pathlib import Path

def run():
    from app.main import main,Window,ROOT
    if "--usb-test" in sys.argv:
        import json
        from app.transport import Pico, serial_ports, identify
        index=sys.argv.index("--usb-test")
        port=sys.argv[index+1]
        report=Path(sys.argv[index+2])
        found,errors=identify([p for p in serial_ports() if p["device"]==port])
        assert found, str(errors)
        link=Pico(port)
        try:
            report.write_text(json.dumps(dict(found=found,errors=errors,version=link.version,
                                             trace=link.drain_trace()),indent=2),encoding="utf-8")
        finally:
            link.close()
        return
    if "--self-test" not in sys.argv:
        main()
        return
    import json,time
    from PySide6.QtWidgets import QApplication
    report=Path(sys.argv[sys.argv.index("--self-test")+1])
    app=QApplication([])
    w=Window()
    def wait():
        deadline=time.monotonic()+10
        while w.pending and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert not w.pending,"operation timeout"
    assert w.profile.currentText()=="Selecione o CI"
    assert not hasattr(w,"mode") and w.link is None
    w.profile.setCurrentText("IR3567B")
    assert w.address.text()=="70" and w.direct_address.text()=="08"
    w.use_simulation=True
    w.connect()
    wait()
    assert w.link and w.link.version==6
    w.address.setText('30')
    w.start_telemetry(1)
    wait()
    assert w.identity_result['complete'] and w.identity_result['kind']=='telemetry'
    report.with_suffix('.telemetry.json').write_text(json.dumps(w.identity_result,indent=2),encoding='utf-8')
    from app.controller_store import current
    chip=current()
    cml=chip['telemetry']['cml_command']
    body=[item['code'] for item in chip['telemetry']['commands'] if item.get('collect', True)]
    expected=len([cml]+[code for code in body if code!=cml]+[cml])
    assert w.telemetry_table.rowCount()==expected
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())]==['Telemetria','Dump','Parâmetros e gravação','Diagnóstico e manutenção']
    assert not w.live_values
    w.tabs.setCurrentWidget(w.telemetry_page)
    w.show()
    app.processEvents()
    assert w.grab().save(str(report.with_suffix(".png")))
    assert not w.windowIcon().isNull()
    report.write_text(json.dumps(dict(ok=True,version="0.53",hardware_access=False)),encoding="utf-8")
    w.close()
    app.quit()

if __name__=="__main__":
    try:run()
    except Exception:
        import tempfile
        target=Path(tempfile.gettempdir())/"VRMBench-error.log"
        target.write_text(traceback.format_exc(),encoding="utf-8")
        if sys.stderr:traceback.print_exc()
        sys.exit(1)
