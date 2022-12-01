# -*- coding: utf-8 -*-
"""Package initialization

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""
import sys
import os

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))


# THOT suite tools
__version__ = "1.0.3"
__date__ = "2022/09"
__author__ = "Eric Blaudez"
__copyright__ = "Copyright 2022, Thales SIX GTS FRANCE, Theresis"
__credits__ = [__author__]
__maintainer__ = __author__
__email__ = "Eric Blaudez"
__status__ = "Development"
