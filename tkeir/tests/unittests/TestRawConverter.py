# -*- coding: utf-8 -*-
"""Test raw converter
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.converters.RawConverter import RawConverter
import os
import unittest


class TestRawConverter(unittest.TestCase):
    def test_converter(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        data_path = os.path.abspath(os.path.join(dir_path, "../data/test-raw/mail"))
        with open(os.path.join(data_path, "mail1.txt"), "rb") as f:
            data = f.read()
            f.close()
            document = RawConverter.convert(data, "file://mail1.txt")
            test_dict = {
                "data_source": "converter-service",
                "source_doc_id": "file://mail1.txt",
                "title": "",
                "content": [
                    "Message-ID: <12882338.1075842025097.JavaMail.evans@thyme>\nDate: Wed, 6 Feb 2002 14:04:29 -0800 (PST)\nFrom: anon1\nTo: anon2\nSubject: Access to UBSWenergy Production Environment\nMime-Version: 1.0\nContent-Type: text/plain; charset=us-ascii\nContent-Transfer-Encoding: 7bit\nX-From: Stephanie \nX-To:  John \nX-cc: \nX-bcc: \nX-Folder: \\ExMerge - John\\Inbox\nX-Origin: J\nX-FileName: john 6-26-02.PST\n\nIMPORTANT- THE IDS BELOW WILL BE YOUR PERMANENT ACCESS TO PRODUCTION\n\nYour PRODUCTION User ID and Password has been set up on UBSWenergy.  Please follow the steps below to access the new environment:\n\nFrom Internet Explorer connect to the UBSWenergy Production Cluster through the following link:\nhttp://remoteservices.netco.enron.com/ica/ubswenergy.ica  (use your UBSWenergy/Enron NT Log In & Password)\n\nFrom the second Start menu,  select appropriate application:\n\nBelow is a special internal use only link for the simulation purposes only to get to the trading area of the website.\nDO NOT PROVIDE THIS LINK TO ANYONE NOT PART OF THE SIMULATION. \n(customers should be directed to go to the direct link www.ubsenergy.com).\n\nhttp://www.ubswenergy.com/site_index.html  (FOR SIMULATION ONLY)\n\nShould you have any questions or issues, please contact me at x33465 or the Call Center at xxx\n\n\nThank you,\nStephanie\n\n"                ],
                "kg": [],
                "error": False,
            }
            self.assertEqual(test_dict, document)
