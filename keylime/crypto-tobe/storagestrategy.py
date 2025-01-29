import sqlite3
from abc import ABC, abstractmethod


class ICertificateStore(ABC):
    @abstractmethod
    def store_certificate(self, common_name, cert, private_key):
        pass

    @abstractmethod
    def get_certificate(self, common_name):
        pass

    @abstractmethod
    def revoke_certificate(self, common_name):
        pass

    @abstractmethod
    def get_ca_certificate(self):
        pass


class SQLiteCertificateStore(ICertificateStore):
    def __init__(self, db_path="cert_store.db"):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS certificates (
                    common_name TEXT PRIMARY KEY,
                    certificate BLOB,
                    private_key BLOB,
                    revoked INTEGER DEFAULT 0
                )
            """
            )
            conn.commit()

    def store_certificate(self, common_name, cert, private_key):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO certificates (common_name, certificate, private_key)
                VALUES (?, ?, ?)
            """,
                (
                    common_name,
                    cert.public_bytes(serialization.Encoding.PEM),
                    private_key.private_bytes(
                        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
                    ),
                ),
            )
            conn.commit()

    def get_certificate(self, common_name):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT certificate FROM certificates WHERE common_name = ?", (common_name,))
            result = cursor.fetchone()
            if result:
                return x509.load_pem_x509_certificate(result[0])
        return None

    def revoke_certificate(self, common_name):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE certificates SET revoked = 1 WHERE common_name = ?", (common_name,))
            conn.commit()
