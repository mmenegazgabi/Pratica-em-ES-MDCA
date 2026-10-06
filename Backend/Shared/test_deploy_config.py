import json
import subprocess
import sys
from pathlib import Path


def export_config(tmp_path, optional=""):
    config = tmp_path / "config.env"
    output = tmp_path / "config.json"
    config.write_text(
        "DATABASE_URL=postgresql://example\n"
        "R2_ACCOUNT_ID=account\n"
        "R2_ACCESS_KEY_ID=key\n"
        "R2_SECRET_ACCESS_KEY=secret\n"
        "R2_BUCKET_NAME=bucket\n"
        "CORS_ORIGINS=https://example.pages.dev\n" + optional,
        encoding="utf-8",
    )
    script = Path(__file__).parents[2] / "scripts" / "export-cloudrun-env.py"
    subprocess.run([sys.executable, str(script), str(config), str(output)], check=True)
    return json.loads(output.read_text(encoding="utf-8"))


def test_omitted_optional_settings_do_not_override_application_defaults(tmp_path):
    config = export_config(tmp_path)
    assert "APP_NAME" not in config
    assert "R2_PUBLIC_URL" not in config
    assert config["R2_BUCKET_NAME"] == "bucket"


def test_configured_optional_settings_are_preserved(tmp_path):
    config = export_config(tmp_path, "APP_NAME=MDCA\nR2_PUBLIC_URL=https://files.example\n")
    assert config["APP_NAME"] == "MDCA"
    assert config["R2_PUBLIC_URL"] == "https://files.example"
