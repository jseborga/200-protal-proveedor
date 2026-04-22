"""Genera un par de claves VAPID (ECDSA P-256) para Web Push.

Uso:
    python scripts/generate_vapid_keys.py

Imprime las variables a agregar en el .env:
    VAPID_PUBLIC_KEY=BK...
    VAPID_PRIVATE_KEY=...
    VAPID_SUBJECT=mailto:admin@tudominio.com

La clave publica (formato URL-safe base64 sin padding) es la que usa
`applicationServerKey` en el navegador. La privada se usa en el backend
con `pywebpush.webpush(...)`.
"""
from __future__ import annotations

import base64


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main() -> None:
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        print("Instala dependencias primero: pip install cryptography pywebpush")
        raise SystemExit(1)

    # Generar clave ECDSA P-256
    priv = ec.generate_private_key(ec.SECP256R1(), default_backend())
    pub = priv.public_key()

    # Private: 32 bytes raw, base64url
    priv_num = priv.private_numbers().private_value
    priv_bytes = priv_num.to_bytes(32, "big")
    priv_b64 = _b64url(priv_bytes)

    # Public: uncompressed point (0x04 || X || Y), 65 bytes
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64 = _b64url(pub_bytes)

    print("# Copia estas lineas a tu .env:")
    print(f"VAPID_PUBLIC_KEY={pub_b64}")
    print(f"VAPID_PRIVATE_KEY={priv_b64}")
    print("VAPID_SUBJECT=mailto:admin@example.com")


if __name__ == "__main__":
    main()
