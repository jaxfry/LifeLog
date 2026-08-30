import io
import os
import zipfile
import json
import glob
from pathlib import Path
from typing import Optional, Tuple

from nacl import signing
from nacl.exceptions import BadSignatureError

from .config import settings
from ..manifest import ExtensionManifest

class ExtensionUploadError(Exception):
    pass


def _read_bytes(file_like) -> bytes:
    if hasattr(file_like, 'read'):
        return file_like.read()
    if isinstance(file_like, (bytes, bytearray)):
        return bytes(file_like)
    raise ExtensionUploadError("Unsupported file-like object")


def verify_signature(archive_bytes: bytes, signature_bytes: bytes, public_key_path: Path) -> bool:
    pub = public_key_path.read_bytes().strip()
    # Support raw 32-byte key or OpenSSH/PEM-like one-line public key content
    try:
        if len(pub) == 32:
            verify_key = signing.VerifyKey(pub)
        else:
            # Try to parse from a text file containing hex/base64; expect hex for simplicity
            try:
                key_raw = bytes.fromhex(pub.decode('utf-8').strip())
                verify_key = signing.VerifyKey(key_raw)
            except Exception as e:
                raise ExtensionUploadError(f"Unsupported public key format in {public_key_path}: {e}")
    except Exception as e:
        raise ExtensionUploadError(f"Failed to load public key {public_key_path}: {e}")

    try:
        verify_key.verify(archive_bytes, signature_bytes)
        return True
    except BadSignatureError:
        return False


def verify_with_trusted_keys(archive_bytes: bytes, signature_bytes: bytes) -> bool:
    keys_dir = Path(settings.TRUSTED_PUBLIC_KEYS_DIR)
    if not keys_dir.exists():
        raise ExtensionUploadError(f"Trusted keys directory not found: {keys_dir}")
    any_ok = False
    for key_file in keys_dir.glob('*.pub'):
        if verify_signature(archive_bytes, signature_bytes, key_file):
            any_ok = True
            break
    if not any_ok:
        raise ExtensionUploadError("Signature verification failed against all trusted public keys")
    return True


def extract_archive(archive_bytes: bytes, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        # require manifest.json at root
        if 'manifest.json' not in zf.namelist():
            raise ExtensionUploadError("manifest.json missing from archive root")
        # Extract to a temp subdir first, then rename atomically
        tmp_dir = dest_dir / ('.tmp_extract')
        if tmp_dir.exists():
            # cleanup previous temp
            for p in tmp_dir.rglob('*'):
                if p.is_file():
                    p.unlink()
            for p in sorted(tmp_dir.rglob('*'), reverse=True):
                if p.is_dir():
                    p.rmdir()
        tmp_dir.mkdir(parents=True, exist_ok=True)
        zf.extractall(tmp_dir)
        # Read manifest to compute canonical path
        manifest_data = json.loads((tmp_dir / 'manifest.json').read_text())
        manifest = ExtensionManifest.model_validate(manifest_data)
        versioned_dir = dest_dir / f"{manifest.slug}-{manifest.version}"
        if versioned_dir.exists():
            # Replace existing version atomically: remove and replace
            for p in versioned_dir.rglob('*'):
                if p.is_file():
                    p.unlink()
            for p in sorted(versioned_dir.rglob('*'), reverse=True):
                if p.is_dir():
                    p.rmdir()
        tmp_dir.rename(versioned_dir)
        return versioned_dir


def load_manifest_from_store(extracted_dir: Path) -> ExtensionManifest:
    mf = extracted_dir / 'manifest.json'
    if not mf.exists():
        raise ExtensionUploadError(f"manifest.json not found in {extracted_dir}")
    return ExtensionManifest.model_validate_json(mf.read_text())


def store_and_register_extension(archive_bytes: bytes, signature_bytes: Optional[bytes] = None) -> Tuple[ExtensionManifest, Path]:
    # Verify signature if provided (and require if production)
    if signature_bytes is not None:
        verify_with_trusted_keys(archive_bytes, signature_bytes)
    else:
        # In production, insist on signature
        if settings.APP_ENV.lower() == 'production':
            raise ExtensionUploadError("Signature is required in production")
    store_root = Path(settings.EXTENSIONS_STORE_PATH)
    store_root.mkdir(parents=True, exist_ok=True)
    extracted = extract_archive(archive_bytes, store_root)
    manifest = load_manifest_from_store(extracted)
    return manifest, extracted
