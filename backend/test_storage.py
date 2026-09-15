import os
import unittest
from unittest.mock import patch

from storage import build_public_file_url, get_r2_config, sanitize_file_name


class StorageConfigTest(unittest.TestCase):
    def test_build_public_file_url_removes_extra_slashes(self):
        url = build_public_file_url("https://pub-example.r2.dev/", "/uploads/teste.pdf")

        self.assertEqual(url, "https://pub-example.r2.dev/uploads/teste.pdf")

    def test_get_r2_config_reads_environment(self):
        with patch.dict(
            os.environ,
            {
                "R2_ACCOUNT_ID": "account-id",
                "R2_ACCESS_KEY_ID": "access-key",
                "R2_SECRET_ACCESS_KEY": "secret-key",
                "R2_BUCKET_NAME": "mdca-arquivos",
                "R2_PUBLIC_URL": "https://pub-example.r2.dev",
            },
            clear=False,
        ):
            config = get_r2_config()

        self.assertEqual(config.bucket_name, "mdca-arquivos")
        self.assertEqual(config.public_url, "https://pub-example.r2.dev")

    def test_sanitize_file_name_keeps_only_safe_characters(self):
        file_name = sanitize_file_name("../Meu Arquivo final!.pdf")

        self.assertEqual(file_name, "Meu_Arquivo_final_.pdf")


if __name__ == "__main__":
    unittest.main()
