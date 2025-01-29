from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID


class CertificateManager:
    def __init__(self, crypto_strategy, storage_backend):
        """
        Certificate Manager that integrates cryptographic strategies and storage.
        :param crypto_strategy: An instance of a cryptographic strategy (e.g., RSACrypto).
        :param storage_backend: An instance of a certificate store backend.
        """
        self.crypto = crypto_strategy  # Implements ICryptoStrategy
        self.storage = storage_backend  # Implements ICertificateStore

        # Load CA certificate if it exists; otherwise, create a new one
        ca_cert, ca_key = self.storage.get_ca_certificate()
        if ca_cert and ca_key:
            self.ca_cert = ca_cert
            self.ca_private_key = ca_key
        else:
            self.ca_private_key, self.ca_cert = self.create_ca_cert()
            self.storage.store_ca_certificate(self.ca_cert, self.ca_private_key)

        self.revoked_certs = []

    def create_ca_cert(self):
        """
        Generates a new CA certificate.
        """
        private_key, public_key = self.crypto.generate_key_pair()

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My CA"),
                x509.NameAttribute(NameOID.COMMON_NAME, "My CA Root Certificate"),
            ]
        )

        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(private_key, hashes.SHA256())
        )

        return private_key, ca_cert

    def generate_signed_cert(self, common_name):
        """
        Creates a new certificate signed by the CA.
        """
        private_key, public_key = self.crypto.generate_key_pair()

        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My Organization"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.ca_cert.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(self.ca_private_key, hashes.SHA256())
        )

        # Store the certificate
        self.storage.store_certificate(common_name, cert, private_key)
        return private_key, cert

    def revoke_certificate(self, common_name):
        """
        Revokes a certificate.
        """
        cert = self.storage.get_certificate(common_name)
        if cert:
            revoked_cert = (
                x509.RevokedCertificateBuilder()
                .serial_number(cert.serial_number)
                .revocation_date(datetime.utcnow())
                .build()
            )
            self.revoked_certs.append(revoked_cert)
            self.storage.revoke_certificate(common_name)

    def generate_crl(self):
        """
        Generates a Certificate Revocation List (CRL).
        """
        crl_builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self.ca_cert.subject)
            .last_update(datetime.utcnow())
            .next_update(datetime.utcnow() + timedelta(days=7))
        )

        for revoked_cert in self.revoked_certs:
            crl_builder = crl_builder.add_revoked_certificate(revoked_cert)

        crl = crl_builder.sign(private_key=self.ca_private_key, algorithm=hashes.SHA256())
        self.storage.store_crl(crl)
        return crl
