import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from app.parameters import loops,save_backup,set_overwrite_prompt
from app.ramtest import experiment
from test_ramtest import Bench

class ParametersTests(unittest.TestCase):
    def test_loop_order(self):
        self.assertEqual([x['raw_hex'] for x in loops(0xEF)],['E','F'])
        self.assertEqual([x['signed_code'] for x in loops(0xEF)],[-2,-1])
    def test_backup_save(self):
        with tempfile.TemporaryDirectory() as d:
            p=save_backup({'value':255},d)
            with open(p,encoding='utf-8') as f:self.assertEqual(json.load(f),{'value':255})
    def test_existing_json_asks_before_replacing(self):
        fixed=datetime(2026,10,2,12,0,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d,patch('app.parameters.datetime') as clock:
            clock.now.return_value=fixed
            previous=set_overwrite_prompt(lambda path:False)
            try:
                first=save_backup({'value':1},d)
                second=save_backup({'value':2},d)
            finally:set_overwrite_prompt(previous)
            self.assertNotEqual(first,second)
            with open(first,encoding='utf-8') as f:self.assertEqual(json.load(f),{'value':1})
            with open(second,encoding='utf-8') as f:self.assertEqual(json.load(f),{'value':2})
            seen=[]
            previous=set_overwrite_prompt(lambda path:seen.append(path.name) or True)
            try:replaced=save_backup({'value':3},d)
            finally:set_overwrite_prompt(previous)
            self.assertEqual(seen,[Path(first).name])
            self.assertEqual(replaced,first)
            with open(first,encoding='utf-8') as f:self.assertEqual(json.load(f),{'value':3})
    def test_backup_failure_blocks_command(self):
        b=Bench([])
        def fail(_):raise OSError('disco cheio')
        r=experiment(b,fail)
        self.assertFalse(r['command_sent']);self.assertEqual(b.calls,0)
        self.assertEqual(r['error'],'disco cheio')
    def test_backup_runs_before_command(self):
        b=Bench([]);seen=[]
        def backup(r):
            self.assertEqual(b.calls,0);self.assertEqual(r['baseline']['value'],255);seen.append(True)
        r=experiment(b,backup)
        self.assertEqual(seen,[True]);self.assertTrue(r['restoration_confirmed'])
