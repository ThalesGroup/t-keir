# -*- coding: utf-8 -*-
"""Test Annotation Configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.DictionaryTrie import Trie, make_trie, prefix_trie, end_trie

import unittest


class TestDictionaryTrie(unittest.TestCase):

    test_data = {
        "a": {
            "b": {
                "c": {True: {"label_info": {"l": {"pos": "POS", "data": [{"data": "1"}], "weight": 1.0}}, "in_vocab": True}},
                "d": {True: {"label_info": {"l": {"pos": "POS2", "data": [{"data": "2"}], "weight": 2.0}}, "in_vocab": True}},
            }
        }
    }

    def test_make_trie(self):
        t = make_trie(set(["abc","abd","efg"]))
        test_d={
            "a":{
                "b":{
                    "c":{"_end_":"_end_"},
                    "d":{"_end_":"_end_"}
                }

            },
            "e":{
                "f":{"g":{"_end_":"_end_"}}
            }
        }
        self.assertEqual(t,test_d)

    def test_prefix_tree(self):
        t = make_trie(set(["abc","abd","efg"]))
        k = prefix_trie(t,"ab")
        sub_tree = {
                    "c":{"_end_":"_end_"},
                    "d":{"_end_":"_end_"}
                }
        self.assertEqual(sub_tree,k)

    def test_end_tree(self):
        self.assertTrue(end_trie({"_end_":"_end_"}))
        self.assertFalse(end_trie( {
                    "c":{"_end_":"_end_"},
                    "d":{"_end_":"_end_"}
                }))

    def test_insert(self):
        t = Trie()
        t.insert(["a", "b", "c"], "l", True, "POS", {"data": "1"}, 1.0)
        t.insert(["a", "b", "d"], "l", True, "POS2", {"data": "2"}, 2.0)
        self.assertTrue(t == TestDictionaryTrie.test_data)
