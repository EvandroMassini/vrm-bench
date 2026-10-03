import unittest
from app.controller_store import select
from app.core import Entry
from app.restore_user import image_from_entries, prepare, program, span, unlock_steps


def _image(start, end, overrides=None):
    values = {address: 0 for address in range(start, end + 1)}
    values.update(overrides or {})
    return values


def _entries(values):
    return [Entry(address, value, 0xFF) for address, value in values.items()]


class FakeLink:
    version = 16

    def __init__(self, memory):
        self.memory = dict(memory)
        self.lines = []
        self._steps = []

    def register_read(self, address, register):
        return dict(value=self.memory.get(register, 0), pec_verified=True)

    def request(self, line):
        self.lines.append(line)
        if line.startswith('TXBEGIN'):
            self._steps = []
            return 'OK TXBEGIN'
        if line.startswith('TXSTEP'):
            self._steps.append(line)
            return 'OK TXSTEP'
        if line == 'TXRUN':
            for step in self._steps:
                parts = step.split()
                if int(parts[2], 16) == 2:
                    self.memory[int(parts[3], 16)] = int(parts[5], 16)
            return 'OK TX 01 FF 01 01'
        return 'ERR'


class RestoreTests(unittest.TestCase):
    def test_ir3567b_image_keeps_only_user_and_requires_every_byte(self):
        profile = select('IR3567B')
        start, end = span(profile)
        self.assertEqual((start, end), (16, 103))
        values = _image(start, end, {20: 0x20})
        values[0] = 0x44
        values[104] = 0x99
        image = image_from_entries(_entries(values), profile)
        self.assertNotIn(0, image)
        self.assertNotIn(104, image)
        self.assertEqual(image[20], 0x20)
        values.pop(40)
        with self.assertRaises(ValueError):
            image_from_entries(_entries(values), profile)

    def test_blank_chip_is_planned_when_the_image_satisfies_the_recipe(self):
        profile = select('IR3567B')
        start, end = span(profile)
        image = _image(start, end, {20: 0x20})
        live = dict(image)
        live[20] = 0
        live.update({113: 0x20, 136: 0x88, 137: 0x88})
        plan = prepare(_entries(image), live, profile)
        self.assertEqual(plan['problems'], [])
        self.assertEqual(plan['writes'], [20])
        self.assertEqual(plan['unlock'], [(228, 0), (229, 0)])

    def test_image_without_the_profile_guard_is_refused_before_any_write(self):
        profile = select('IR3567B')
        start, end = span(profile)
        image = _image(start, end)
        live = dict(image)
        live.update({113: 0x20, 136: 0x88, 137: 0x88})
        plan = prepare(_entries(image), live, profile)
        self.assertTrue(plan['problems'])
        self.assertIn('14', plan['problems'][0])

    def test_program_clears_comanche_locks_and_writes_only_different_user_bytes(self):
        profile = select('IR3567B')
        start, end = span(profile)
        image = _image(start, end, {20: 0x20})
        live = dict(image)
        live[20] = 0
        live.update({113: 0x20, 136: 0x88, 137: 0x88})
        plan = prepare(_entries(image), live, profile)
        plan['live'] = live
        link = FakeLink({228: 0x80, 229: 0})
        report = program(link, plan)
        self.assertTrue(report['ok'], report['error'])
        self.assertEqual(report['written'], [228, 20])
        self.assertEqual(link.memory[228], 0)
        self.assertEqual(link.memory[20], 0x20)
        self.assertNotIn(229, report['written'])

    def test_ir35217_restore_has_no_extra_unlock(self):
        profile = select('IR35217')
        self.assertEqual(unlock_steps(profile), [])
        start, end = span(profile)
        self.assertEqual((start, end), (36, 150))
