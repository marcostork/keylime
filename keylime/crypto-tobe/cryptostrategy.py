from abc import ABC, abstractmethod
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class ICryptoStrategy(ABC):
    @abstractmethod
    def generate_key_pair(self) -> Tuple:
        pass


class RSACrypto(ICryptoStrategy):
    def __init__(self, private_key=None, public_key=None):
        if private_key:
            self._private_key = private_key
        else:
            # Generate a new private key if none is provided
            self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        self._public_key = public_key or self._private_key.public_key()

    def generate_key_pair(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return private_key, private_key.public_key()

    def sign(self, data: bytes) -> bytes:
        """
        Signs the given data using RSA private key and returns the signature.
        """
        signature = self._private_key.sign(
            data, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
        )
        return signature

    def validate(self, data: bytes, signature: bytes) -> bool:
        """
        Validates the signature against the given data using the RSA public key.
        Returns True if the signature is valid, otherwise raises an exception.
        """
        try:
            self._public_key.verify(
                signature,
                data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    def export_keys(self) -> Tuple[bytes, bytes]:
        """
        Exports the private and public keys in PEM format.
        """
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        return private_pem, public_pem

    @staticmethod
    def load_private_key(pem_data: bytes):
        """
        Loads an RSA private key from a PEM-formatted byte string.
        """
        return serialization.load_pem_private_key(pem_data, password=None)

    @staticmethod
    def load_public_key(pem_data: bytes):
        """
        Loads an RSA public key from a PEM-formatted byte string.
        """
        return serialization.load_pem_public_key(pem_data)
