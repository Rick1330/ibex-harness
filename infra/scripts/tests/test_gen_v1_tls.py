"""Exercise TLS repair against real OpenSSL certificates and POSIX ACLs."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "gen-v1-tls.sh"


class TLSRepairTest(unittest.TestCase):
    def run_command(self, *args):
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout

    def digest(self, name):
        return hashlib.sha256((self.target / name).read_bytes()).hexdigest()

    def generate(self):
        self.run_command("bash", str(SCRIPT), str(self.target))
        acl = self.run_command("getfacl", "-cpn", str(self.target / "auth.key"))
        self.assertIn("user:10001:r--", acl)
        self.assertIn("other::---", acl)
        for name in ("ca.key", "edge.key"):
            self.assertEqual((self.target / name).stat().st_mode & 0o777, 0o600)

    def test_reuse_and_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            self.target = Path(directory) / "certs"
            self.generate()
            original = {name: self.digest(name) for name in ("ca.crt", "auth.crt", "edge.crt")}
            self.generate()
            self.assertEqual(original, {name: self.digest(name) for name in original})
            for purpose, san in (
                ("clientAuth", "DNS:auth,IP:127.0.0.1"),
                ("serverAuth", "DNS:auth.attacker,IP:127.0.0.10"),
                ("serverAuth", "DNS:auth,IP:127.0.0.10"),
            ):
                with self.subTest(purpose=purpose, san=san):
                    csr = Path(directory) / "leaf.csr"
                    ext = Path(directory) / "leaf.ext"
                    ext.write_text(f"extendedKeyUsage={purpose}\nsubjectAltName={san}\n")
                    self.run_command("openssl", "req", "-new", "-key", str(self.target / "auth.key"),
                                     "-out", str(csr), "-subj", "/CN=auth")
                    self.run_command("openssl", "x509", "-req", "-in", str(csr),
                                     "-CA", str(self.target / "ca.crt"), "-CAkey", str(self.target / "ca.key"),
                                     "-set_serial", "42", "-days", "1", "-extfile", str(ext),
                                     "-out", str(self.target / "auth.crt"))
                    invalid = self.digest("auth.crt")
                    self.generate()
                    self.assertNotEqual(invalid, self.digest("auth.crt"))
                    self.assertEqual(original["ca.crt"], self.digest("ca.crt"))
                    self.assertEqual(original["edge.crt"], self.digest("edge.crt"))
                    self.run_command("openssl", "verify", "-purpose", "sslserver", "-CAfile",
                                     str(self.target / "ca.crt"), str(self.target / "auth.crt"))


if __name__ == "__main__":
    unittest.main()
