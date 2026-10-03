import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app import controller_store as store,transactions as tx
from app.profile_schema import validate,ProfileError
from app.generic_operations import change_byte,commit,reload_image,enable
from app.slot_commit import user_plan,image_token

class Bench:
    version=16
    def __init__(self):
        self.profile=store.current();self.calls=[];self.steps=[];self.fail=False;self.restore=True
        self.values={a:0 for a in self.profile['dump']['addresses']}
        self.values.update({self.profile['mtp']['user_pointer_register']:self.profile['mtp']['user_sentinel'],self.profile['verify']['crc_register']:0})
        for s in self.profile['recipes'].get('commit',[]):
            if s['op']=='assert':self.values[s['register']]=s['value']
    def observe(self):return dict(sda_low_samples=0,scl_low_samples=0,changes=0)
    def set_speed(self,speed):pass
    def pm_read(self,*args):return dict(raw_hex=self.profile['identity']['model_hex'],pec_verified=True)
    def telemetry_read(self,address,command):
        m=self.profile['protocol']['mapping']
        value=m['enabled_mask']|int(self.profile['bus']['direct'],16) if command==m['command'] else 0
        return dict(value_raw=value,pec_verified=True)
    def register_read(self,address,reg):return dict(value=self.values.get(reg,0),pec_verified=True)
    def request(self,cmd):
        self.calls.append(cmd)
        if cmd.startswith('TXBEGIN'):self.steps=[];return 'OK TXBEGIN'
        if cmd.startswith('TXSTEP'):
            self.steps.append([int(x,16) for x in cmd.split()[2:]]);return 'OK TXSTEP'
        if cmd=='TXRUN':
            if self.fail:return f'OK TX 00 02 01 {int(self.restore):02X}'
            for op,reg,mask,val,*_ in self.steps:
                if op==2:self.values[reg]=(self.values.get(reg,0)&~mask)|val
                if op==3 and val>=self.profile['mtp']['opcode_base']:
                    self.values[self.profile['mtp']['user_pointer_register']]=val-self.profile['mtp']['opcode_base']
            return 'OK TX 01 FF 01 01'
        raise AssertionError(cmd)

class GenericTests(unittest.TestCase):
    def setUp(self):store.load();store.select('IR3567B');self.tmp=tempfile.TemporaryDirectory()
    def tearDown(self):self.tmp.cleanup();store.load();store.select('IR3567B')
    def image(self,b,d):return dict(stable=True,values={f'{a:02X}':f'{b.values[a]:02X}' for a in store.current()['dump']['addresses']})
    def test_profiles_validate(self):
        for name in store.names():validate(store.get(name))
    def test_incomplete_and_broken_file_do_not_hide_valid_profiles(self):
        folder=Path(self.tmp.name);p=copy.deepcopy(store.current());p['id']='NEW'
        (folder/'valid.json').write_text(json.dumps(p),encoding='utf-8')
        (folder/'bad.json').write_text('{',encoding='utf-8')
        (folder/'empty.json').write_text('{"id":"BAD"}',encoding='utf-8')
        self.assertEqual(list(store.load(folder)),['NEW']);self.assertEqual(len(store.errors()),2)
    def test_duplicate_id_is_reported(self):
        folder=Path(self.tmp.name);p=store.current()
        for n in ('a','b'):(folder/f'{n}.json').write_text(json.dumps(p),encoding='utf-8')
        store.load(folder);self.assertEqual(len(store.errors()),1)
    def test_invalid_descriptors_are_rejected(self):
        mutations=[lambda p:p.update(schema_version=2),lambda p:p['protocol']['identity'].update(mask=0),lambda p:p['fields'][0].update(length=9),lambda p:p['telemetry']['commands'][0].update(decoder='python'),lambda p:p['recipes'].pop('commit'),lambda p:p['recipes']['commit'][0].update(value=256),lambda p:p['mtp'].update(user_capacity=0)]
        for mutate in mutations:
            p=copy.deepcopy(store.current());mutate(p)
            with self.assertRaises((ProfileError,KeyError)):validate(p)
    def test_future_model_changes_addresses_and_identity_without_engine_change(self):
        p=copy.deepcopy(store.current());p.update(id='FUTURE');p['bus']['direct']='09';p['protocol']['identity']={'register':200,'mask':255,'value':90};p['protocol']['guards']=[]
        store._chips['FUTURE']=p;store.select('FUTURE');b=Bench()
        r=tx.execute(b,[dict(op='assert',register=44,mask=255,value=12)])
        self.assertTrue(r['complete']);self.assertTrue(b.calls[0].startswith('TXBEGIN 09 C8 FF 5A'))
        self.assertIn('TXSTEP 00 00 2C FF 0C 02 00 00 01',b.calls)
    def test_old_firmware_never_receives_transaction(self):
        b=Bench();b.version=15
        with self.assertRaises(ValueError):tx.change(b,38,0,1)
        self.assertEqual(b.calls,[])
    def test_stale_ram_is_rejected_before_transaction(self):
        b=Bench();b.values[38]=2;r=change_byte(b,self.tmp.name,38,1,{38:0})
        self.assertFalse(r['complete']);self.assertFalse(r['command_sent']);self.assertFalse(b.calls)
    def test_masked_ram_write_and_readback(self):
        b=Bench();b.values[38]=0;r=change_byte(b,self.tmp.name,38,1,{38:0})
        self.assertTrue(r['complete']);self.assertEqual(b.values[38],1);self.assertTrue(Path(r['backup_path']).exists())
    def test_blocked_write_is_not_uploaded(self):
        b=Bench()
        with self.assertRaises(ValueError):tx.change(b,136,136,72)
        self.assertFalse(b.calls)
    def test_salem_identity_and_slot_capacity(self):
        store.select('IR35217');b=Bench()
        self.assertEqual(user_plan(15)['left'],7);self.assertEqual(user_plan(5)['opcode'],70)
        tx.execute(b,[dict(op='assert',register=36,mask=255,value=0)])
        self.assertIn('FB FF 5F',b.calls[0])
    def test_commit_both_profiles_and_exactly_one_slot(self):
        for name in store.names():
            store.select(name);b=Bench();base=dict(b.values)
            r=commit(b,self.tmp.name,self.image,baseline=base)
            self.assertTrue(r['complete'],r);self.assertEqual(r['slots_consumed'],1)
            self.assertEqual(b.calls.count('TXRUN'),1)
    def test_no_slots_no_command(self):
        b=Bench();b.values[167]=8;r=commit(b,self.tmp.name,self.image,baseline=dict(b.values))
        self.assertFalse(r['complete']);self.assertFalse(b.calls)
    def test_changed_token_and_snapshot_required(self):
        b=Bench();base=dict(b.values);b.values[38]=1
        r=commit(b,self.tmp.name,self.image,'changed','invalid',base)
        self.assertFalse(r['complete']);self.assertFalse(b.calls)
        token=image_token(self.image(b,None)['values']);r=commit(b,self.tmp.name,self.image,'changed',token,base)
        self.assertTrue(r['complete'],r)
    def test_failed_commit_does_not_retry_or_read_map_again(self):
        b=Bench();b.fail=True;b.restore=False;count=[]
        def reader(*a):count.append(1);return self.image(*a)
        r=commit(b,self.tmp.name,reader,baseline=dict(b.values))
        self.assertFalse(r['complete']);self.assertFalse(r['restored']);self.assertEqual(len(count),1);self.assertEqual(b.calls.count('TXRUN'),1)
    def test_no_commit_without_session_baseline(self):
        b=Bench();r=commit(b,self.tmp.name,self.image)
        self.assertFalse(r['complete']);self.assertFalse(b.calls)
    def test_reload_does_not_program_slot(self):
        b=Bench();before=b.values[167];r=reload_image(b,self.tmp.name,self.image)
        self.assertTrue(r['complete'],r);self.assertEqual(b.values[167],before)
    def test_failure_restoration_is_reported(self):
        b=Bench();b.fail=True;b.restore=False;r=enable(b)
        self.assertFalse(r['restoration_confirmed']);self.assertFalse(r['complete'])
