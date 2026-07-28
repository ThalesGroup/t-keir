"""Task information
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import os
import socket
import time


class TaskInfo:
    def __init__(self, task_name=None, task_version=None, task_date=None):
        """ Create task info 
        Args:
        - task_name is the name of the task
        - task_version is the version of the task
        - task_date is the date of task run
        """
        self._version = task_version
        self._date = task_date
        self._name = task_name

    def addInfo(self, tkeir_doc):
        """ Add task information into tkeir_doc """
        if "tasks-info" not in tkeir_doc:
            tkeir_doc["tasks-info"] = []
        tkeir_doc["tasks-info"].append(
            {
                "os": list(os.uname()),
                "hostname": socket.gethostname(),
                "host": socket.gethostbyname(socket.gethostname()),
                "execution-date": time.strftime("%b %d %Y %H:%M:%S", time.gmtime()),
                "task-version": self._version,
                "task-development-date": self._date,
                "task-name": self._name,
            }
        )
        return tkeir_doc
