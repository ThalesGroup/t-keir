# -*- coding: utf-8 -*-
"""Package initialization

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2021 by THALES
"""

import os
import sys

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))


# MS Tagger service
__version_morphosyntax__ = "2.0.0"
__date_morphosyntax__ = "2022/09"
