import unittest
import threading
from app.transport import identify, Pico, ADDRESSES
from app.scan import scan_bus

class DiscoveryTests(unittest.TestCase):
    def test_filter_close_and_two_picos(self):
        calls,closed=[],[]
        class Fake:
            version=2
            def __init__(self,port):self.port=port;calls.append(port)
            def close(self):closed.append(self.port)
        ports=[dict(device="COM1",vid=0x1234),dict(device="COM2",vid=0x2E8A),dict(device="COM3",vid=0x2E8A)]
        found,errors=identify(ports,Fake)
        self.assertEqual(calls,["COM2","COM3"])
        self.assertEqual(closed,calls)
        self.assertEqual(len(found),2)
        self.assertFalse(errors)

    def test_busy_candidate_does_not_stop_discovery(self):
        def broken(port):raise OSError("ocupada")
        found,errors=identify([dict(device="COM2",vid=0x2E8A)],broken)
        self.assertFalse(found)
        self.assertIn("ocupada",errors[0])

    def test_full_scan_excludes_reserved(self):
        class Fake:
            def probe(self,address):
                self.seen.append(address)
                return address==0x30
            seen=[]
        link=Fake()
        result=scan_bus(link,threading.Event(),lambda *args:None)
        self.assertTrue(result["complete"])
        self.assertEqual(result["addresses"],[0x30])
        self.assertEqual(link.seen,list(ADDRESSES))
        self.assertNotIn(0x0C,link.seen)
        self.assertEqual(len(link.seen),111)

    def test_cancel_preserves_partial_results(self):
        stop=threading.Event()
        class Fake:
            def probe(self,address):return True
        result=scan_bus(Fake(),stop,lambda *args:stop.set())
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["checked"],1)
        self.assertEqual(result["addresses"],[8])
        self.assertFalse(result["complete"])

    def test_error_preserves_partial_and_stops(self):
        class Fake:
            def probe(self,address):
                if address==9:raise RuntimeError("ERR SCL_TIMEOUT")
                return True
        result=scan_bus(Fake(),threading.Event(),lambda *args:None)
        self.assertEqual(result["addresses"],[8])
        self.assertEqual(result["checked"],1)
        self.assertEqual(result["error"],"ERR SCL_TIMEOUT")

    def test_protocol_probe_and_legacy(self):
        p=Pico.__new__(Pico)
        p.version=1
        with self.assertRaises(ValueError):p.probe(0x30)
        p.version=2
        p.request=lambda c: "OK ACK" if c=="PROBE 30" else "OK NACK"
        self.assertTrue(p.probe(0x30))
        self.assertFalse(p.probe(0x31))
        with self.assertRaises(ValueError):p.probe(0)

if __name__=="__main__":unittest.main()
