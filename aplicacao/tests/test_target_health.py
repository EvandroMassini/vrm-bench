import unittest
from unittest.mock import Mock
from app.target_health import verify_target

class HealthTests(unittest.TestCase):
    def test_model_and_pec_required(self):
        for response in ({'raw_hex':'44','pec_verified':False},{'raw_hex':'00','pec_verified':True}):
            link=Mock();link.observe.return_value=dict(sda_low_samples=0,scl_low_samples=0,changes=0);link.pm_read.return_value=response
            with self.assertRaisesRegex(ValueError,'alimentação'):verify_target(link,112,'IR3567B')
    def test_valid_device_only_reads(self):
        link=Mock();link.observe.return_value=dict(sda_low_samples=0,scl_low_samples=0,changes=0)
        link.pm_read.return_value=dict(raw_hex='44',pec_verified=True)
        verify_target(link,112,'IR3567B');link.pm_read.assert_called_once_with(112,154,True,False);link.request.assert_not_called()
    def test_busy_bus_blocks_model_read(self):
        link=Mock();link.observe.return_value=dict(sda_low_samples=1,scl_low_samples=0,changes=0)
        with self.assertRaises(ValueError):verify_target(link,112,'IR3567B')
        link.pm_read.assert_not_called()
