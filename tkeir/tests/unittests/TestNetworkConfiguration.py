# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.NetworkConfiguration import NetworkConfiguration
import json
import os
import unittest


class TestNetworkConfiguration(unittest.TestCase):
    def test_load(self):
        """Test load with file function"""
        test_dict = {
            "network": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            }
        }
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)

        fh = open("/tmp/cfg.json")
        netconfig = NetworkConfiguration()
        netconfig.load(fh)
        fh.close()
        self.assertEqual(netconfig.configuration, test_dict)
        netconfig.clear()
        os.environ["HOST_ENVNAME"] = "localhost"
        test_dict = {
            "network": {
                "host": "localhost",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            }
        }
        fh = open("/tmp/cfg.json")
        netconfig.load(fh)
        fh.close()
        self.assertEqual(netconfig.configuration, test_dict)

    def test_loads(self):
        """Test load with dict function"""
        test_dict = {
            "network": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            }
        }
        netconfig = NetworkConfiguration()
        netconfig.loads(test_dict)
        self.assertEqual(netconfig.configuration, test_dict)

        os.environ["HOST_ENVNAME"] = "localhost"
        test_dict = {
            "network": {
                "host": "localhost",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            }
        }
        netconfig.clear()
        netconfig.loads(test_dict)
        self.assertEqual(netconfig.configuration, test_dict)

        test_dict = {
            "badconf": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            }
        }
        netconfig.clear()
        try:
            netconfig.loads(test_dict)
            self.assertTrue(False)
        except:
            self.assertTrue(True)

    def test_clear(self):
        test_dict = {
            "network": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            }
        }
        netconfig = NetworkConfiguration()
        netconfig.loads(test_dict)
        netconfig.clear()
        self.assertEqual(netconfig.configuration, None)
