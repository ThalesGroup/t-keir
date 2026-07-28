# -*- coding: utf-8 -*-
"""Trie structure for lexical resources

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

from os import sysconf
from thot.core.ThotLogger import ThotLogger


def make_trie(words:set)->dict:
    """
    Create et TRIE structure
    E.G: the set ["abc","abd","efg"]
    become the dict: {
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

    :param words(set) : a set of word
    :return a TRIE structure of the list of words
    
    """
    root = dict()
    for word in words:
        current_dict = root
        for letter in word:
            current_dict = current_dict.setdefault(letter, {})
        current_dict["_end_"] = "_end_"
    return root


def prefix_trie(trie:dict, word:str)->dict:
    """
    Get the subtree after the preix
    E.G: 
    trie: {
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
    word:"ab"
    return : {
                                "c":{"_end_":"_end_"},
                                "d":{"_end_":"_end_"}
                            }

    :param trie(dict) : TRIE structure
    :param word(str) : the prefix
    :return a TRIE structure of the list of words or None if there is no prefix
    
    """
    current_dict = trie
    for letter in word:
        if letter not in current_dict:
            return None
        current_dict = current_dict[letter]
    return current_dict


def end_trie(trie:dict)->bool:
    return "_end_" in trie


class Trie(dict):
    "Create mulitple word expression"
    LEAF = True

    def __init__(self, strings=None):
        """
        Initialize module
        :param strings: list of strings to add
        """
        super(Trie, self).__init__()
        self.current_string = ""
        if strings:
            for string in strings:
                self.current_string = string["pattern"]
                if self.current_string:
                    self.insert(
                        string["pattern"], string["label"], string["in_vocab"], string["pos"], string["data"], string["weight"]
                    )
                else:
                    ThotLogger.warning("Empty entry")

    def insert(self, string, label, in_vocab, pos, data, weight):
        """
        insert new string
        :param string: the string to insert
        :param label : label of string
        :param in_vocab : string is in spacy vocabulary
        :param pos : part of speech
        :param data : associated data
        :param weight : weight associated to string
        """
        if len(string):
            self[string[0]].insert(string[1:], label, in_vocab, pos, data, weight)
        else:
            # mark the string is complete
            if Trie.LEAF not in self:
                self[Trie.LEAF] = {"label_info": dict(), "in_vocab": False}
            if label not in self[Trie.LEAF]["label_info"]:
                self[Trie.LEAF]["label_info"][label] = {"pos": pos, "data": [], "weight": weight}
            already_inserted = False
            if (Trie.LEAF in self) and (label in self[Trie.LEAF]["label_info"]):
                for label_info_data_i in self[Trie.LEAF]["label_info"][label]["data"]:
                    if label_info_data_i == data:
                        already_inserted = True
                        break
            if not already_inserted:
                self[Trie.LEAF]["label_info"][label]["data"].append(data)
            else:
                ThotLogger.warning(
                    "Data " + str(label_info_data_i) + " already inserted in word '" + str(self.current_string) + "'"
                )
            self[Trie.LEAF]["in_vocab"] = in_vocab

    def __missing__(self, key):
        """
        create sub tree in case of missing
        :param key : the key
        """
        self[key] = Trie()
        return self[key]
