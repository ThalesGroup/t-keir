# -*- coding: utf-8 -*-
"""Test Common configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

import unittest
import os
from thot.core.CommonConfiguration import CommonConfiguration
from copy import deepcopy


class TestCommonConfiguration(unittest.TestCase):

    def test__replace_string_by_type(self):
        test_dict = {"test-int": "10", "test-float": "10.3", "test-bool1": "False","test-bool2":"true"}
        cfg1 = CommonConfiguration._replace_string_by_type(test_dict, "test-int")
        cfg2 = CommonConfiguration._replace_string_by_type(test_dict, "test-float")
        cfg3 = CommonConfiguration._replace_string_by_type(test_dict, "test-bool1")
        cfg4 = CommonConfiguration._replace_string_by_type(test_dict, "test-bool2")
        self.assertTrue(isinstance(cfg1["test-int"],int))
        self.assertTrue(isinstance(cfg1["test-float"],float))
        self.assertTrue(isinstance(cfg1["test-bool1"],bool))
        self.assertTrue(isinstance(cfg1["test-bool2"],bool))


    def test_affect_associated_environment(self):
        test_dict = {"host": "0.0.0.0", "port": 8080, "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"}}
        try_affectation = deepcopy(test_dict)
        CommonConfiguration.affect_associated_environment(try_affectation)
        self.assertEqual(try_affectation, test_dict)
        os.environ["HOST_ENVNAME"] = "localhost"
        os.environ["PORT_ENVNAME"] = "8080"
        CommonConfiguration.affect_associated_environment(try_affectation)
        self.assertEqual(try_affectation["host"], "localhost")
        self.assertEqual(try_affectation["port"], 8080)

    def test_go_to_configuration_field(self):
        test_dict = {
            "converter": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            }
        }
        test_new_config1 = {"associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"}}
        test_new_config2 = {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"}
        new_config1 = CommonConfiguration.go_to_configuration_field(
            configuration=test_dict, path=["converter", "associate-environment"]
        )
        self.assertEqual(new_config1, test_new_config1)
        new_config2 = CommonConfiguration.go_to_configuration_field(
            configuration=test_dict, path=["converter", "associate-environment"], keep_last_field=False
        )
        self.assertEqual(new_config2, test_new_config2)
