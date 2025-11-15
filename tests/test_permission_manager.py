"""Tests for PermissionManager async helpers."""

import asyncio
import tempfile
from pathlib import Path
from unittest import TestCase

from modules.permission_manager import PermissionManager, PermissionScope, PermissionStatus


class TestPermissionManagerAsync(TestCase):
    """Validate executor-backed helpers for permissions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "permissions.db"
        self.manager = PermissionManager(db_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.close()

    def test_async_round_trip(self) -> None:
        asyncio.run(
            self.manager.set_permission_async(
                "TestAgent",
                PermissionScope.TOOL_BASH_RUN,
                PermissionStatus.ALLOW,
            )
        )
        status = asyncio.run(
            self.manager.check_permission_async(
                "TestAgent", PermissionScope.TOOL_BASH_RUN
            )
        )
        self.assertEqual(status, PermissionStatus.ALLOW)

    def test_async_get_all_and_revoke(self) -> None:
        asyncio.run(
            self.manager.set_permission_async(
                "TestAgent",
                PermissionScope.TOOL_BASH_RUN,
                PermissionStatus.DENY,
            )
        )
        all_permissions = asyncio.run(
            self.manager.get_all_permissions_async("TestAgent")
        )
        self.assertIn("tool.bash.run", all_permissions.get("TestAgent", {}))

        asyncio.run(
            self.manager.revoke_permission_async(
                "TestAgent", PermissionScope.TOOL_BASH_RUN
            )
        )
        status = asyncio.run(
            self.manager.check_permission_async(
                "TestAgent",
                PermissionScope.TOOL_BASH_RUN,
            )
        )
        self.assertEqual(status, PermissionStatus.ASK)
