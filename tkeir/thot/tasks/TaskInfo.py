"""Title: Task information

T-KEIR core package module.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import os
import socket
import time


def _hostname() -> str:
    """Return the current host name for task metadata.

    Example:
        >>> isinstance(_hostname(), str)
        True
    """
    return socket.gethostname()


def _host_address() -> str:
    """Return a resolvable host address for task metadata.

    Example:
        >>> _host_address().count(".") == 3
        True
    """
    hostname = _hostname()
    for candidate in (hostname, "localhost"):
        try:
            return socket.gethostbyname(candidate)
        except OSError:
            continue
    return "127.0.0.1"


class TaskInfo:
    """TaskInfo container.

    Example:
        >>> from thot.tasks.TaskInfo import TaskInfo
        >>> callable(TaskInfo)
        True
    """

    def __init__(self, task_name=None, task_version=None, task_date=None):
        """Create task metadata helper.

        Args:
            task_name: Logical task name.
            task_version: Task version string.
            task_date: Task release date string.

        Example:
            >>> info = TaskInfo("converter", "1.0", "2026-01-01")
            >>> info._name
            'converter'
        """
        self._version = task_version
        self._date = task_date
        self._name = task_name

    def addInfo(self, tkeir_doc):
        """Append task execution metadata to a T-KEIR document.

        Args:
            tkeir_doc: Document dict to enrich.

        Returns:
            The same document with a ``tasks-info`` entry appended.

        Example:
            >>> doc = TaskInfo("converter", "1.0", "2026-01-01").addInfo({})
            >>> doc["tasks-info"][-1]["task-name"]
            'converter'
        """
        if "tasks-info" not in tkeir_doc:
            tkeir_doc["tasks-info"] = []
        tkeir_doc["tasks-info"].append(
            {
                "os": list(os.uname()),
                "hostname": _hostname(),
                "host": _host_address(),
                "execution-date": time.strftime(
                    "%b %d %Y %H:%M:%S", time.gmtime()
                ),
                "task-version": self._version,
                "task-development-date": self._date,
                "task-name": self._name,
            }
        )
        return tkeir_doc
