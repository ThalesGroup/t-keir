"""Title: Task Info

Tests for task metadata helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from unittest.mock import patch

from thot.tasks.TaskInfo import TaskInfo, _host_address


class TestTaskInfo:
    def test_add_info_includes_task_metadata(self):
        document = {}
        TaskInfo(
            task_name="converter",
            task_version="2.0.0",
            task_date="2026-01-01",
        ).addInfo(document)

        assert len(document["tasks-info"]) == 1
        entry = document["tasks-info"][0]
        assert entry["task-name"] == "converter"
        assert entry["task-version"] == "2.0.0"
        assert entry["hostname"]
        assert entry["host"]

    @patch("thot.tasks.TaskInfo.socket.gethostbyname", side_effect=OSError)
    def test_host_address_falls_back_when_hostname_is_unresolvable(
        self, _mock
    ):
        assert _host_address() == "127.0.0.1"
