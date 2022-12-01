# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import os
import mimetypes
import traceback
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup
import re
import hashlib
from thot.core.Utils import is_email
from thot.core.Constants import exception_error_and_trace
from thot.core.ThotLogger import ThotLogger
from thot.tasks.converters.RawConverter import RawConverter


def subtable(table_word):
    """ remove tags and fqdn email
    Args:
        table_word : table of word
    Returns:
        modified table of words
    """
    for k in range(len(table_word)):
        table_word[k] = re.sub("[<\[].*?[>\]]", "", table_word[k])
        table_word[k] = re.sub('["\[].*?["\]]', "", table_word[k])
        table_word[k] = re.sub(" @[A-Za-z0-9]+", "", table_word[k])
    return table_word


def addWithHash(hash_entries, document, S, P, O):
    """ Add triple Subject, Property Object into tkeir doc structure
    Args:
        hash_entries : hash table to avoid duplicate
        document : tkeir document
        S : subject
        P : predicate
        O : Object
    """
    m = hashlib.md5()
    m.update(str(S + "##" + P + "##" + O).encode())
    hash_id = m.hexdigest()
    if hash_id not in hash_entries:
        document["kg"].append(
            {
                "subject": {"content": S, "lemma_content": S, "positions": [-1], "label_content": ""},
                "value": {"content": O, "lemma_content": O, "positions": [-1], "label_content": ""},
                "property": {"content": P, "lemma_content": P, "positions": [-1], "label_content": ""},
                "automatically_fill": True,
                "confidence": 1.0,
                "weight": 0.0,
                "field_type": "mail-header",
            }
        )
        hash_entries.add(hash_id)


def addToKG(hash_entries, document, msg, header_attributes, relation, mailNameFrom, mailAdressFrom, call_context):
    """add entry into knowledge graph

        Args:
            hash_entries (set): existing entry (avoid duplicate)
            document (dict): tkeir document
            msg (dict) : mail message
            header_attributes : header attributes
            relation : relation type
            mailNameFrom : name of people (mail name)
            mailAddressFrom : mail address
            call_context =  call conttext for log       

        Returns:
            nothing : fill document
        """
    try:
        for header_attribute in header_attributes:
            if header_attribute in msg:
                try:
                    name_list = re.findall(r"([^<]+)[^,]+", msg[header_attribute])
                    mail_list = re.findall(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", msg[header_attribute])
                    for name_i in name_list:
                        name_i = name_i.strip()
                        names_i = name_i.split(",")
                        if name_i and ("@" not in name_i):
                            if mailNameFrom:
                                namefroms = mailNameFrom.split(",")
                                for namef_i in namefroms:
                                    for ni in names_i:
                                        addWithHash(hash_entries, document, namef_i, relation, ni.strip())
                            elif mailAdressFrom:
                                namefroms = mailAdressFrom.split(",")
                                for namef_i in namefroms:
                                    for ni in names_i:
                                        addWithHash(hash_entries, document, namef_i, relation, ni.strip())
                            names = name_i.split(",")
                            for ni in names:
                                addWithHash(hash_entries, document, ni.strip(), "rel:instanceof", "person")

                    for name_i in mail_list:
                        names_i = name_i.split(",")
                        if mailAdressFrom:
                            namefroms = mailAdressFrom.split(",")
                            for namef_i in namefroms:
                                for ni in names_i:
                                    addWithHash(hash_entries, document, namef_i, relation, ni.strip())
                except Exception as e:
                    ThotLogger.error(
                        "Failed to add in kg:" + mailAdressFrom + " " + mailNameFrom + " " + header_attribute,
                        context=call_context,
                        trace=exception_error_and_trace(e, traceback.format_exc()),
                    )

    except Exception as e:
        ThotLogger.error(
            "Failed to add in kg:" + mailAdressFrom + " " + mailNameFrom,
            context=call_context,
            trace=exception_error_and_trace(e, traceback.format_exc()),
        )


class EmailConverter:
    @staticmethod
    def convert(data: bytes, source_doc_id, call_context=None):
        """convert email to tkeir content

        Args:
            data (bytes): mail data
            source_doc_id (str): mail id

        Returns:
            [dict]: tkeir document
        """
        ThotLogger.debug("Call Email Converter", context=call_context)
        msg = BytesParser(policy=policy.default).parsebytes(data)
        document = {
            "data_source": "converter-service",
            "source_doc_id": source_doc_id,
            "title": msg["subject"],
            "content": "",
            "kg": [],
            "error": False,
        }
        mailNameFrom = ""
        mailAdressFrom = ""
        hash_entries = set()
        for header_attribute in ["From", "from", "X-From"]:
            if header_attribute in msg:
                try:
                    if not mailNameFrom:
                        mailNameFrom = re.findall(r"([^<]+)[^,]+", msg[header_attribute])
                        if mailNameFrom and ("@" in mailNameFrom[0]):
                            mailNameFrom = ""
                        if mailNameFrom:
                            mailNameFrom = mailNameFrom[0].strip()
                            addWithHash(hash_entries, document, mailNameFrom, "rel:instanceof", "person")
                    if not mailAdressFrom:
                        mailAdressFrom = re.findall(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", msg[header_attribute])

                        if mailAdressFrom:
                            mailAdressFrom = mailAdressFrom[0]
                            addWithHash(hash_entries, document, mailAdressFrom, "rel:instanceof", "email")
                except Exception as e:
                    ThotLogger.error(
                        "Message error:" + str(msg),
                        context=call_context,
                        trace=exception_error_and_trace(e, traceback.format_exc()),
                    )
                    raise (e)

        addToKG(hash_entries, document, msg, ["To", "to", "X-To"], "rel:mailto", mailNameFrom, mailAdressFrom, call_context)
        addToKG(hash_entries, document, msg, ["Cc", "cc", "X-cc"], "rel:mailcc", mailNameFrom, mailAdressFrom, call_context)
        addToKG(hash_entries, document, msg, ["Bcc", "bcc", "X-bcc"], "rel:mailbcc", mailNameFrom, mailAdressFrom, call_context)
        if "Date" in msg:
            maildate = msg["Date"]
            if maildate:
                addWithHash(hash_entries, document, maildate, "rel:instanceof", "date")
        richest = msg.get_body()
        contentIsExtracted = False
        try:
            if richest and ("content-type" in richest):
                
                if richest["content-type"].maintype == "text":
                    body = ""
                    if richest["content-type"].subtype == "plain":
                        for line in richest.get_content().splitlines():
                            body = body + "\n" + line
                    elif richest["content-type"].subtype == "html":
                        body = richest
                    else:
                        raise ValueError("Don't know how to display {}".format(richest.get_content_type()))
                    contentIsExtracted = True
                    soup = BeautifulSoup(body, "html.parser")
                    document["content"] = [
                        str(soup.get_text())
                    ]

                elif richest["content-type"].content_type == "multipart/related":
                    body = richest.get_body(preferencelist=("html"))
                    for part in richest.iter_attachments():
                        fn = part.get_filename()
                        if fn:
                            extension = os.path.splitext(part.get_filename())[1]
                        else:
                            extension = mimetypes.guess_extension(part.get_content_type())
                        # print(part.get_content())
                        addWithHash(hash_entries, document, fn, "rel:attachment", "file")
                    contentIsExtracted = True
                    document["content"] = [
                        soup.get_text()
                    ]
                else:
                    contentIsExtracted = False
        except:
            contentIsExtracted = False
        if not contentIsExtracted:
            raw = RawConverter.convert(data, source_doc_id)
            if raw:
                if raw["content"]:
                    content = raw["content"]
                    if isinstance(raw["content"], list):
                        content = ""
                        for item in raw["content"]:
                            content = content + " " + item
                    content_text = soup.get_text()
                    content = content_text
                    if isinstance(content_text, list):
                        content = ""
                        for item in content_text:
                            content = content + content_text
                    document["content"] = [content.replace("**_", "").replace("_**", "").replace("**", " ").replace("#", " ")]
                else:
                    document["content"] = [""]
        return document
