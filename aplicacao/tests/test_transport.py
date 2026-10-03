import unittest
from app.transport import Pico

class FakeSerial:
    def __init__(self, response):
        self.response, self.sent, self.closed = response, [], False
    def write(self, data):
        self.sent.append(data)
    def read_until(self, end, size):
        return self.response
    def close(self):
        self.closed = True

class TransportTests(unittest.TestCase):
    def bridge(self, response):
        p = Pico.__new__(Pico)
        p.serial = FakeSerial(response)
        return p
    def test_read_wire(self):
        p = self.bridge(b"OK B0\r\n")
        self.assertEqual(p.read(0x30,0x24),0xB0)
        self.assertEqual(p.serial.sent,[b"READ 30 24\n"])
    def test_error_closes(self):
        for response in (b"ERR I2C_READ\n", b"OK 20", b""):
            with self.subTest(response=response):
                p = self.bridge(response)
                with self.assertRaises((RuntimeError,TimeoutError)):
                    p.read(0x30,0x24)
                self.assertTrue(p.serial.closed)
    def test_reserved_no_io(self):
        p = self.bridge(b"OK 00\n")
        with self.assertRaises(ValueError):
            p.read(0x0C,0x24)
        self.assertEqual(p.serial.sent,[])
