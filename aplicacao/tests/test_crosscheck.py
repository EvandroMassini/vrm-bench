import unittest
from threading import Event
from app.transport import Simulated
from app.crosscheck import compare_paths
from app.registers import capture

class Board(Simulated):
    def read(self,address,register):
        if address!=8:raise ValueError('wrong direct address')
        return register^0x55

class CrosscheckTests(unittest.TestCase):
    def setUp(self):
        from app.controller_store import select
        select('IR3567B')
    def test_extended_catalog_capture(self):
        from app.catalog import EXTENDED,LABELS
        registers=[int(r,16) for r in EXTENDED.split()]
        self.assertEqual(len(registers),17)
        self.assertEqual(len(set(registers)),17)
        self.assertTrue(set(registers).isdisjoint({0x93,0x94,0x9A,0x9B,0x9C,0x9D,0x9E,0x9F}))
        r=compare_paths(Board([]),0x30,8,100,registers,'community',Event(),lambda _:None)
        self.assertTrue(r['all_equal']);self.assertTrue(r['complete'])
        self.assertEqual(len(r['rows']),34)
        self.assertEqual(len(r['register_catalog']['registers']),len(LABELS))

    def run_capture(self,board=None,direct=8,event=None,progress=lambda _:None):
        return compare_paths(board or Board([]),0x30,direct,100,[13,34,35,36,37],'test',event or Event(),progress)

    def test_four_values_agree(self):
        r=self.run_capture()
        self.assertTrue(r['complete']);self.assertTrue(r['all_equal'])
        self.assertEqual(len(r['rows']),10)
        self.assertIsNone(r['rows'][0]['direct']['pec_verified'])

    def test_address_mismatch_stops_direct_read(self):
        r=self.run_capture(direct=9)
        self.assertFalse(r['complete']);self.assertEqual(r['rows'],[])
        self.assertIn('difere',r['error'])

    def test_mismatch_is_reported(self):
        class Different(Board):
            def read(self,*_):return 0
        r=self.run_capture(Different([]))
        self.assertTrue(r['complete']);self.assertFalse(r['all_equal'])

    def test_low_lines_stop_before_commands(self):
        class Low(Board):
            def observe(self):return dict(sda_low_samples=10000,scl_low_samples=10000,changes=0)
            def pm_read(self,*_):raise AssertionError('must not transmit')
        for r in (self.run_capture(Low([])),capture(Low([]),0x30,100,[13],'test',Event(),lambda _:None)):
            self.assertIn('BUS_NOT_IDLE',r['error'])
            self.assertIn('alimentada',r['guidance'])
            self.assertFalse(r['complete'])

    def test_partial_error_retained(self):
        class Broken(Board):
            def read(self,*_):raise ValueError('ERR BUS_BUSY')
        r=self.run_capture(Broken([]))
        self.assertEqual(r['rows'][0]['pmbus']['value'],13^0x55)
        self.assertEqual(r['rows'][0]['status'],'error')
        self.assertIn('alimentada',r['guidance'])

    def test_cancel_keeps_partial(self):
        event=Event()
        r=self.run_capture(event=event,progress=lambda _:event.set())
        self.assertTrue(r['cancelled']);self.assertEqual(len(r['rows']),1)
