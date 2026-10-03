import unittest
from unittest.mock import patch
from app.transport import Pico

class HandshakeTests(unittest.TestCase):
    def test_dtr_enabled_before_open_and_lf(self):
        instances=[]
        class Serial:
            def __init__(self,**kwargs):
                self.kwargs=kwargs
                self.dtr=False
                self.rts=True
                self.closed=False
                self.sent=[]
                instances.append(self)
            def open(self):
                if not self.dtr:raise RuntimeError("DTR required")
            def reset_input_buffer(self):pass
            def write(self,b):self.sent.append(b)
            def read_until(self,*args):return b"OK INFINEON-PICO 2 READONLY\r\n"
            def close(self):self.closed=True
        with patch("serial.Serial",Serial),patch("app.transport.time.sleep"):
            p=Pico("COM7")
            self.assertEqual(p.version,2)
            self.assertEqual(instances[0].sent,[b"HELLO\n"])
            self.assertFalse(instances[0].rts)
            self.assertEqual(instances[0].kwargs["baudrate"],115200)
            p.close()
            self.assertTrue(instances[0].closed)
