# -*- coding: utf-8 -*-
"""Utilitary functions

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import os
import errno
import gzip
import json
import re
import random
import string
from spacy.tokens import Doc, Token
import threading


import ctypes

def timeit(f):
    """ Macro allowing to compute running time
    Args:
    - f : the function to run
    Returns:
        The function result
    """
    def timed(*args, **kw):

        ts = time.time()
        result = f(*args, **kw)
        te = time.time()

        print('func:%r took: %2.4f sec' % \
          (f.__name__, te-ts))
        return result

    return timed

def terminate_thread(thread):
    """Terminates a python thread from another thread.

    :param thread: a threading.Thread instance
    """
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("nonexistent thread id")
    elif res > 1:
        # """if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class TimeLimitExpired(Exception):
    pass


def timelimit(timeout, func, args=(), kwargs={}):
    """Run func with the given timeout. If func didn't finish running
    within the timeout, raise TimeLimitExpired
    """

    class FuncThread(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self)
            self.result = None

        def run(self):
            self.result = func(*args, **kwargs)

        def stop(self):
            terminate_thread(self)

    it = FuncThread()
    it.start()
    it.join(timeout)
    if it.is_alive():
        it.stop()
        raise TimeLimitExpired()
    else:
        return it.result


def set_if_not_exists(d: dict, att, v):
    if att not in d:
        d[att] = v


def check_pid(pid):
    """Check For the existence of a unix pid."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python ≥ 2.5
        if exc.errno != errno.EEXIST or (not os.path.isdir(path)):
            raise


def type_to_bool(entry):
    if isinstance(entry, str):
        return entry.lower() in ["true", "1", "t", "y", "yes", "on"]
    if isinstance(entry, bool):
        return entry
    if isinstance(entry, int) or isinstance(entry, float):
        return entry > 0
    raise ValueError("Cannot convert to bool")


def generate_id(prefix="default", length=32):
    qid = "".join([random.choice(string.ascii_letters + string.digits) for _ in range(length)])
    qid = (
        prefix + "-" + qid + "-" + str(os.getppid()) + "-" + str(os.getpid()) + "-" + str(threading.current_thread().getName())
    )
    return qid


def is_numeric(literal):
    """Return whether a literal can be parsed as a numeric value
    :param literal : entry to query
    : return True if literal is numeric
    """
    if isinstance(literal, int) or isinstance(literal, float) or isinstance(literal, complex):
        return True
    if isinstance(literal, str):
        return literal.replace(".", "", 1).isdigit()
    return False


# for custom mails use: '^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w+$'

# Define a function for
# for validating an Email
def is_email(email):
    return re.search("^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$", email.lower())


def str_to_uni(str_catch):
    """convert string to unicode"""
    if len(str_catch) > 0:
        merged_token = "0x" + str_catch[1:]
        return chr(int(merged_token, 0))
    return ""


class ThotTokenizerToSpacy:
    def __init__(self, vocab, config: dict = None, call_context=None):
        self.vocab = vocab
        self.config = config
        Token.set_extension("advanced_tag", default={"is-compound": False, "data": {}}, force=True)

    def _flattern_table(self, text):
        """Flattern recurcive table
        Args:
            text (list): tokenized entry (generally from tokenizer service)

        Returns:
            [list] : list of tokens
        """
        flattern_text = []
        flattern_sentence = []
        flattern_data = []
        if isinstance(text, list):
            for text_i in text:
                ftable = self._flattern_table(text_i)
                flattern_text = flattern_text + ftable[0]
                flattern_sentence = flattern_sentence + ftable[1]
                flattern_data = flattern_data + ftable[2]
            return [flattern_text, flattern_sentence, flattern_data]
        data = {}
        if ("mwe" in text) and ("data" in text["mwe"]):
            data = text["mwe"]["data"]
        return [[text["token"]], [text["start_sentence"]], [data]]

    def __call__(self, text, pre_tagging_with_concept=False):
        """Call fake tokenizer : in tagger service stream is supposed already tokenized

        Args:
            text (list): tokenized entry (generally from tokenizer service)

        Returns:
            [spacy.tokens.Doc]: the spacy doc format of the text
        """
        [words, sentences, data] = self._flattern_table(text)
        pos_tags = []
        tags = []
        advanced_tags = []
        pos_mapping = {
            "NOUN": "NN",
            "PROPN": "NNP",
        }
        for data_i in range(len(data)):
            is_concept = False
            pos = ""
            advanced_tags.append([])
            for label in data[data_i]:
                if "data" in data[data_i][label]:
                    for data_entry in data[data_i][label]["data"]:
                        if ("type" in data_entry) and (data_entry["type"] == "concept"):
                            if len(advanced_tags[-1]) == 0:
                                advanced_tags[-1].append({label: None})
                            if label not in advanced_tags[-1][-1]:
                                advanced_tags[-1][-1]({label: None})
                            advanced_tags[-1][-1][label] = data_entry
                            is_concept = True
                    if is_concept and ("pos" in data[data_i][label]):
                        pos = data[data_i][label]["pos"]
                        break
            pos_tags.append(pos)
            if pos in pos_mapping:
                tags.append(pos_mapping[pos])
            else:
                tags.append("")
        doc = Doc(self.vocab, words=words, pos=pos_tags, tags=tags)
        token_i = 0
        for token in doc:
            token.is_sent_start = sentences[token_i]
            token._.advanced_tag = advanced_tags[token_i]
            token_i = token_i + 1
        return doc


def get_elastic_url(configuration):
    es_scheme = "http"
    es_verify_certs = True
    if type_to_bool(configuration["network"]["use_ssl"]):
        es_scheme = "https"
    if not configuration["network"]["verify_certs"]:
        es_verify_certs = False
    else:
        es_verify_certs = configuration["network"]["verify_certs"]
    if isinstance(es_verify_certs, str):
        if es_verify_certs.lower() == "true":
            es_verify_certs = True
        else:
            es_verify_certs = False

    es_user = None
    es_password = None
    if "auth" in configuration["network"]:
        if "user" in configuration["network"]["auth"]:
            es_user = configuration["network"]["auth"]["user"]
        if "password" in configuration["network"]["auth"]:
            es_password = configuration["network"]["auth"]["password"]
    es_url = es_scheme + "://"
    if es_user and es_password:
        es_url = es_url + es_user + ":" + es_password + "@"
    es_url = es_url + configuration["network"]["host"] + ":" + str(configuration["network"]["port"])
    return (es_url, es_verify_certs)


def save_json(data: dict, filename: str, zip_file: bool = False):
    # save compressed
    if zip_file:
        json_data = json.dumps(data, indent=2)
        with gzip.open(filename, "wb") as f:
            f.write(json_data.encode("utf-8"))
            f.close()
    else:
        with open(filename, "w", encoding="utf-8") as output_f:
            json.dump(data, output_f, indent=2, sort_keys=True, ensure_ascii=False)
            output_f.close()


def load_json(filename: str, zip_file: bool = False):
    load_error = True
    data = dict()
    if not zip_file:
        try:
            with open(filename, encoding="utf-8") as json_f:
                data = json.load(json_f)
                json_f.close()
                load_error = False
        except Exception as e:
            pass
    if load_error:
        with gzip.open(filename, "rb") as gzip_f:
            gdata = gzip_f.read()
            data = json.loads(gdata)
            gzip_f.close()
    return data
