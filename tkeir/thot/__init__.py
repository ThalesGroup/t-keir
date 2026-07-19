"""THOT suite tools — T-KEIR core package.

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2026 by THALES
"""

import os
import sys

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

# Package metadata (single source for ``import thot``)
__version__ = "2.0.0"
__date__ = "2026/07"
__author__ = "Eric Blaudez"
__copyright__ = "Copyright 2026, Thales SIX GTS FRANCE"
__credits__ = [__author__]
__maintainer__ = __author__
__email__ = "Eric Blaudez"
