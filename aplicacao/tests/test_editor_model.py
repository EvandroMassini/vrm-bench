import unittest
from app import editor_model as m

class EditorTests(unittest.TestCase):
    def setUp(self):self.values={0x14:0x22,0x17:0xA4,0x18:0xA4,0x26:0xFF,0x22:100,0x23:100,0x31:0,0x32:100}
    def test_blank_preserves_every_byte(self):self.assertEqual(m.plan(self.values,{'LOOP_1_VID_OFFSET':' '}),({},[]))
    def test_offset_preserves_other_loop(self):
        changes,_=m.plan(self.values,{'LOOP_1_VID_OFFSET':'-6,25'})
        self.assertEqual(changes,{0x26:0xEF})
    def test_two_loops_share_one_write(self):
        changes,_=m.plan(self.values,{'LOOP_1_VID_OFFSET':'-6,25','LOOP_2_VID_OFFSET':'6,25'})
        self.assertEqual(changes,{0x26:0xE0})
    def test_bad_step_range_nan_and_hex_rejected(self):
        for value in ('-6.2','999','nan','inf','EF','0x10'):
            with self.subTest(value=value),self.assertRaises(ValueError):m.plan(self.values,{'LOOP_1_VID_OFFSET':value})
    def test_mode_dependency(self):
        self.values[0x14]=0
        with self.assertRaises(ValueError):m.plan(self.values,{'LOOP_1_VID_OFFSET':'-6,25'})
    def test_frequency_roundtrip(self):
        f=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_SW_PERIOD')
        self.assertEqual(m.encode(f,f'{m.numeric(f,self.values):.4f}',self.values),100)
        with self.assertRaises(ValueError):m.encode(f,'500',self.values)
    def test_vboot(self):
        f=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_VBOOT')
        self.assertAlmostEqual(m.numeric(f,self.values),1.1)
        changes,_=m.plan(self.values,{'LOOP_1_VBOOT':'1,15'})
        self.assertEqual(changes,{0x17:0xA0})
        with self.assertRaises(ValueError):m.plan(self.values,{'LOOP_1_VBOOT':'0'})
    def test_register_14_stays_closed_and_explains_why(self):
        mode=next(f for f in m.FIELDS if f['symbol']=='APPLICATION_MODE')
        phases=next(f for f in m.FIELDS if f['symbol']=='LOOPS_CONFIGURATION')
        sequence=next(f for f in m.FIELDS if f['symbol']=='SEQUENCE_MODE')
        loop2=next(f for f in m.FIELDS if f['symbol']=='LOOP_2_OCP_THR')
        self.assertIn('61',m.lock_reason(mode,{}))
        self.assertIn('não cria fases',m.lock_reason(phases,{}))
        self.assertIn('não é gravado',m.lock_reason(sequence,{0x14:0x22}))
        self.assertFalse(m.editable(sequence,{0x14:0x22}))
        self.assertIn('não tem fases',m.lock_reason(loop2,{0x14:0x22,0x34:0}))
        self.assertIsNone(m.lock_reason(next(f for f in m.FIELDS if f['symbol']=='OCP_MODE'),{0x32:0}))

    def test_dependent_temperature(self):
        changes,_=m.plan(self.values,{'TEMP_MAX':'100','OTP_THRESH':'110'})
        self.assertEqual(changes,{0x32:144,0x31:10})
        self.assertEqual(changes[0x32]&3,self.values[0x32]&3)

    def test_salem_enum_uses_the_same_bit_insert(self):
        from app.controller_store import select
        select('IR35217')
        try:
            field=next(item for item in m.FIELDS if item['symbol']=='ocp_mode')
            self.assertTrue(field['conversion']['editable'])
            self.assertEqual(field['conversion']['source'], 'UtilityModule.UpdateBufferValue')
            changes, rows=m.plan({72: 0}, {'ocp_mode': 2})
            self.assertEqual(changes, {72: 2})
            self.assertEqual(rows[0]['after'], next(choice['text'] for choice in field['choices'] if choice['code']==2))
            closed=next(item for item in m.FIELDS if item['symbol']=='dvid_alert_mode')
            self.assertFalse(closed['conversion']['editable'])
            self.assertFalse(m.editable(closed, {137: 0}))
        finally:
            select('IR3567B')

