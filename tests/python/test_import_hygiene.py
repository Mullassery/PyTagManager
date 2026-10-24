from __future__ import annotations

import subprocess
import sys
import textwrap


def test_base_cli_import_does_not_load_optional_dependencies():
    code = textwrap.dedent(
        """
        import sys
        import pytagmanager.cli

        optional = sorted(
            name for name in ("yaml", "playwright") if name in sys.modules
        )
        assert optional == [], optional
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
