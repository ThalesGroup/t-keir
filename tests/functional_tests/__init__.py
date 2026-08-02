"""Title: functional tests package init

Automated tests for T-KEIR (unit / functional).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import os
import sys

dir_path = os.path.dirname(os.path.realpath(__file__))
# tests/functional_tests → repo root, then tkeir package root
repo_root = os.path.abspath(os.path.join(dir_path, "../.."))
tkeir_dir = os.path.join(repo_root, "tkeir")
sys.path.insert(0, repo_root)
sys.path.insert(0, tkeir_dir)
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))
