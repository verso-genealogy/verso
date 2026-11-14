"""verso.ru.pipeline.translate — what importing it costs."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.codepaths import child_env


def test_importing_the_pipeline_does_not_load_the_translator(tmp_path: Path):
    """~20 CLIs answer --help without translating anything; a re-export of the pipeline
    must not make each of them import the translator first."""
    code = ("import sys, verso.core.pipeline.load, verso.core.pipeline.config, verso.ru.pipeline.translate, verso.ru.cli.generate_tf; "
            "print('verso.ru.targets.geni.translator' in sys.modules)")
    done = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=child_env(), capture_output=True, text=True,
                          check=True)
    assert done.stdout.strip() == "False"
