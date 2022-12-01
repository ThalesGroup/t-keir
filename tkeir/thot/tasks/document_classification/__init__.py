# -*- coding: utf-8 -*-
"""Package initialization

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2021 by THALES
"""
import sys
import os

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))


# Converter service
__version_document_classification__ = "1.0.3"
__date_document_classification__ = "2022/09"
