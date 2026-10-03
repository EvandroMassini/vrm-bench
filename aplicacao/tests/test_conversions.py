import unittest
from app import conversions as c
from app import editor_model as m
from app.engineering import convert
from app.field_map import FIELDS

class ConversionTests(unittest.TestCase):
    def setUp(self):
        from app.controller_store import select
        select('IR3567B')
        self.values={0x14:0x02,0x1A:0xAB,0x1B:0xCD,0x1C:0xEF,0x1D:0x5A,0x24:40,0x25:20,0x33:0x45,0x3D:0x3C,0x38:0x01,0x4D:0xE5,0x4E:0x00,0x61:0x00,0x63:0x40}

    def test_descriptors_match_phase_table(self):
        for field in FIELDS:
            if field['symbol'] in c.PHASE_BITS:
                self.assertEqual(c.PHASE_BITS[field['symbol']],(field['address'],field['offset'],field['length']))

    def test_loadline_roundtrip_and_code_zero(self):
        loop1=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_LL_REG')
        self.assertEqual(m.display(loop1,{0x24:0}),'1 mΩ (código 0; o código linear de 1 mΩ é 40)')
        self.assertEqual(m.encode(loop1,'1',{0x24:0}),40)
        self.assertEqual(m.encode(loop1,'0,025',{0x24:1}),1)
        loop2=next(f for f in m.FIELDS if f['symbol']=='LOOP_2_LL_REG')
        self.assertEqual(m.encode(loop2,'1',self.values),20)
        self.assertAlmostEqual(m.numeric(loop2,self.values),1)
        with self.assertRaises(ValueError):m.encode(loop1,'0,01',self.values)

    def test_ocp_depends_on_phase_count_and_preserves_ovp(self):
        fast=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_OCP_THR')
        self.assertEqual(m.display(fast,self.values),'60 A')
        changes,_=m.plan(self.values,{'LOOP_1_OCP_THR':'48','OVP_THRESH':'250'})
        self.assertEqual(changes[0x33]&0xE0,0x40)
        self.assertEqual(changes[0x33]&0x1F,4)
        self.values[0x14]=0x08
        self.assertFalse(m.editable(fast,self.values))

    def test_slow_ocp_zero_and_neighbor_bits(self):
        slow=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_SLOW_IPH_MAX')
        self.assertEqual(m.display(slow,{0x14:0x02,0x4D:0xE0}),'Desabilitado')
        changes,_=m.plan({0x14:0x02,0x4D:0xE5},{'LOOP_1_SLOW_IPH_MAX':'Desabilitado'})
        self.assertEqual(changes[0x4D],0xE0)

    def test_voltage_protections_are_the_official_list(self):
        ovp=next(f for f in m.FIELDS if f['symbol']=='OVP_THRESH')
        for index,mv in enumerate(c.RELATIVE_MV):
            self.assertEqual(m.encode(ovp,str(mv),self.values),index)
            self.assertEqual(m.display(ovp,{0x33:index<<5}),f'{mv} mV')
        with self.assertRaises(ValueError):m.encode(ovp,'300',self.values)

    def test_vmax_svi_scale_preserves_the_other_loop(self):
        first=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_VMAX')
        self.assertEqual(m.display(first,{0x3D:0x30}),'1,14375 V')
        changes,_=m.plan({0x3D:0x3C},{'LOOP_1_VMAX':'0,80625'})
        self.assertEqual(changes[0x3D],0x0C)
        with self.assertRaises(ValueError):m.encode(first,'1,2',{0x3D:0})

    def test_phase_threshold_is_cumulative_and_keeps_other_nibble(self):
        phase1=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_PHASE1_THRESH')
        phase2=next(f for f in m.FIELDS if f['symbol']=='LOOP_1_PHASE2_DELTA')
        self.assertEqual(m.display(phase1,{0x1A:0xAB}),'20 A')
        self.assertEqual(m.display(phase2,{0x1A:0xAB}),'42 A')
        changes,_=m.plan({0x1A:0xAB},{'LOOP_1_PHASE2_DELTA':'24'})
        self.assertEqual(changes[0x1A],0xA2)
        changes,_=m.plan({0x1A:0xAB},{'LOOP_1_PHASE1_THRESH':'10','LOOP_1_PHASE2_DELTA':'24'})
        self.assertEqual(changes[0x1A],0x57)

    def test_modes_are_named_and_ocp_mode_is_listed(self):
        loops=next(f for f in m.FIELDS if f['symbol']=='LOOPS_CONFIGURATION')
        mode=next(f for f in m.FIELDS if f['symbol']=='DEVICE_PERSONALITIES')
        svi=next(f for f in m.FIELDS if f['symbol']=='SVI2_MODE')
        pwm=next(f for f in m.FIELDS if f['symbol']=='PWM_EN_ATS')
        ocp_mode=next(f for f in m.FIELDS if f['symbol']=='OCP_MODE')
        self.assertEqual(m.display(loops,{0x14:2}),'6 + 0 fases')
        self.assertEqual(m.display(loops,{0x14:8}),'0 + 0 fases')
        self.assertFalse(m.editable(loops,{0x14:2}))
        self.assertEqual(m.display(mode,{0x14:0x20,0x61:0x40}),'GPU')
        self.assertEqual(m.display(svi,{0x63:0x40}),'SVI2')
        self.assertFalse(m.editable(mode,{0x14:0x20,0x61:0}))
        changes,_=m.plan({0x38:0xFF},{'PWM_EN_ATS':'Tri-state'})
        self.assertEqual(changes[0x38],0xDF)
        self.assertEqual(m.display(ocp_mode,{0x32:0}),'Desliga imediatamente')
        changes,_=m.plan({0x32:0},{'OCP_MODE':2})
        self.assertEqual(changes[0x32],2)

    def test_report_names_the_source(self):
        text,source=convert('LOOP_1_VMAX',3,{0x3D:{'value':0x30}})
        self.assertEqual(text,'1,14375 V')
        self.assertIn('ramo SVI',source)
        self.assertIn('Desliga após 7 tentativas',convert('OCP_MODE',1,{})[0])

    def test_phase_rows_use_two_amp_code_and_loop_counts(self):
        rows=c.phase_rows({0x14:0x22,0x1E:0x10,0x33:0x05,0x4D:0x00})
        self.assertEqual(len(rows),8)
        self.assertEqual(rows[0][:4],('Fase 1','Loop 1','10 A','Desabilitado'))
        self.assertIn('fator 1,016',rows[0][4])
        self.assertTrue(rows[1][4].startswith('0 · igual'))
        self.assertEqual(rows[5][1],'Loop 1')
        self.assertEqual(rows[6][1],'Fora da configuração')
        self.assertEqual(rows[6][2],'—')
