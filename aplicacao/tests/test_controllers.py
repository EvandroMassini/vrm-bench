import json
import tempfile
import unittest
from pathlib import Path
from app.controller_store import load
from app.transport import port_caption

class ControllerFileTests(unittest.TestCase):
    def test_each_json_file_becomes_one_controller(self):
        folder = Path(tempfile.mkdtemp())
        (folder / 'ZZ.json').write_text(json.dumps(dict(__import__('app.controller_store',fromlist=['get']).get('IR3567B'),id='ZZ')), encoding='utf-8')
        (folder / 'AA.json').write_text(json.dumps(dict(__import__('app.controller_store',fromlist=['get']).get('IR3567B'),id='AA')), encoding='utf-8')
        try:
            found = load(folder)
            self.assertEqual(list(found), ['AA', 'ZZ'])
        finally:
            load()

    def test_port_caption_drops_the_pico_identity(self):
        self.assertEqual(port_caption(dict(device='COM7', description='Pico - Board CDC (COM7)')),
                         'COM7 — Dispositivo Serial USB (COM7)')
        self.assertEqual(port_caption(dict(device='COM3', description='Dispositivo Serial USB (COM3)')),
                         'COM3 — Dispositivo Serial USB (COM3)')
