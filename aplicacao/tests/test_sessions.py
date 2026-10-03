import unittest,json,tempfile
from pathlib import Path
from threading import Event
from app.crosscheck import compare_paths
from app.sessions import compare_files
from test_crosscheck import Board

class SessionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data=compare_paths(Board([]),0x30,8,100,[13,34],'test',Event(),lambda _:None)
        self.data['source']='Pico USB'
        self.save('a');self.save('b')
    def tearDown(self):self.temp.cleanup()
    def save(self,name):
        (self.root/name).write_text(json.dumps(self.data),encoding='utf-8')
    def compare(self):return compare_files(self.root/'a',self.root/'b')
    def test_equal(self):self.assertTrue(self.compare()['all_equal'])
    def test_changed(self):
        for row in self.data['rows']:
            if row['register_hex']=='22':
                for key in ('pmbus','direct'):row[key].update(value=1,raw_hex='01')
        self.save('b');self.assertEqual(self.compare()['changed_count'],1)
    def test_reject_partial(self):
        self.data['complete']=False;self.save('b')
        with self.assertRaises(ValueError):self.compare()
    def test_reject_disagreement(self):
        self.data['rows'][0]['direct']['value']=0;self.save('b')
        with self.assertRaises(ValueError):self.compare()
    def test_reject_same_file(self):
        with self.assertRaises(ValueError):compare_files(self.root/'a',self.root/'a')
    def test_missing_register(self):
        self.data['requested_registers']=[13]
        self.data['rows']=[r for r in self.data['rows'] if r['register_hex']=='0D']
        self.save('b');self.assertEqual(self.compare()['missing_count'],1)
