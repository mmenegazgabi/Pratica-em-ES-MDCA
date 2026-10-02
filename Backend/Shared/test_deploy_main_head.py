import os
import subprocess
from pathlib import Path

import pytest


def check_main(tmp_path, tested_sha, main_sha, fail=False):
    # Substitui apenas a consulta externa à API GitHub; o guard real é executado.
    gh = tmp_path / "gh"
    gh.write_text(
        '#!/usr/bin/env bash\n'
        'if [[ "$1" != "api" || "$2" != "repos/mmenegazgabi/Pratica-em-ES-MDCA/git/ref/heads/main" || "$3" != "--jq" || "$4" != ".object.sha" ]]; then exit 26; fi\n'
        'if [[ "$MDCA_TEST_API_FAILURE" == "1" ]]; then exit 25; fi\n'
        'printf "%s\\n" "$MDCA_TEST_MAIN_SHA"\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
               GITHUB_REPOSITORY="mmenegazgabi/Pratica-em-ES-MDCA",
               GITHUB_SHA=tested_sha, GITHUB_OUTPUT=str(output),
               MDCA_TEST_MAIN_SHA=main_sha, MDCA_TEST_API_FAILURE="1" if fail else "0")
    script = Path(__file__).parents[2] / "scripts" / "check-main-head.sh"
    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    return result, output.read_text(encoding="utf-8")


@pytest.mark.parametrize("tested_sha,expected", [
    ("1111111111111111111111111111111111111111", "current=true\n"),
    ("2222222222222222222222222222222222222222", "current=false\n"),
])
def test_deploy_guard_authorizes_only_the_current_main_commit(tmp_path, tested_sha, expected):
    result, output = check_main(tmp_path, tested_sha, "1111111111111111111111111111111111111111")
    assert result.returncode == 0, result.stderr
    assert output == expected


def test_deploy_guard_fails_closed_when_github_api_fails(tmp_path):
    result, output = check_main(tmp_path, "1111111111111111111111111111111111111111", "", fail=True)
    assert result.returncode == 25
    assert output == ""
