# Trusted Public Keys for Extension Signing

This directory contains Ed25519 public keys used to verify extension package signatures.

## Security Model

**Extension signing is REQUIRED in production** (`APP_ENV=production`).

- Development (`APP_ENV=development`): Unsigned extensions are allowed for faster iteration
- Production: All uploaded extensions MUST be signed by a key in this directory

## Key Format

Place one or more `.pub` files in this directory. Each file should contain either:

1. **Raw 32-byte Ed25519 public key** (binary)
2. **Hex-encoded public key** (64 hex characters as text)

## Generating a Signing Key Pair

```bash
# Install PyNaCl if not already installed
pip install pynacl

# Generate a new Ed25519 key pair
python3 << 'EOF'
from nacl import signing
import binascii

# Generate new signing key
signing_key = signing.SigningKey.generate()
verify_key = signing_key.verify_key

# Save private key (KEEP SECRET!)
with open('extension_signing_key.priv', 'wb') as f:
    f.write(signing_key.encode())

# Save public key (distribute to servers)
with open('extension_signing_key.pub', 'wb') as f:
    f.write(verify_key.encode())

print("✓ Generated key pair:")
print(f"  Private key: extension_signing_key.priv (KEEP SECRET!)")
print(f"  Public key: extension_signing_key.pub")
print(f"  Public key (hex): {binascii.hexlify(verify_key.encode()).decode()}")
EOF
```

## Signing an Extension Package

```bash
# Sign the extension zip file
python3 << 'EOF'
from nacl import signing

# Load your private key
with open('extension_signing_key.priv', 'rb') as f:
    signing_key = signing.SigningKey(f.read())

# Read the extension package
with open('my-extension.zip', 'rb') as f:
    package_bytes = f.read()

# Create detached signature
signature = signing_key.sign(package_bytes).signature

# Save signature
with open('my-extension.zip.sig', 'wb') as f:
    f.write(signature)

print("✓ Created signature: my-extension.zip.sig")
EOF
```

## Uploading a Signed Extension

```bash
# Upload with signature verification
curl -X POST "http://localhost:8000/internal/extensions/upload" \
  -F "package=@my-extension.zip" \
  -F "signature=@my-extension.zip.sig" \
  -F "approve=true"
```

## Trust Model

- **System owner controls this directory**: Only keys added here can sign valid extensions
- **No revocation mechanism yet**: Remove a `.pub` file to distrust a signer (affects future uploads only)
- **Multiple signers supported**: Any key in this directory can sign extensions
- **Use case examples**:
  - `lifelog-official.pub`: Your official first-party extensions
  - `trusted-partner.pub`: Vetted third-party developers
  - `personal.pub`: Your personal signing key

## Security Best Practices

1. **Keep private keys secure**: Never commit `.priv` files to git
2. **Use different keys per trust level**: Separate keys for official vs. community extensions
3. **Rotate keys periodically**: Generate new keys annually, phase out old ones
4. **Audit extension code before signing**: Signature only proves origin, not safety
5. **Store private keys encrypted**: Use password-protected key stores in production

## Current Status

**⚠️ This directory is currently empty.**

- Development mode allows unsigned extensions
- **Before deploying to production**, generate and add at least one trusted public key
- See scripts in `server/scripts/` for packaging helpers
