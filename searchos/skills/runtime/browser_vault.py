"""按站点加密浏览器目录；本机密钥与密文独立保存。"""
from __future__ import annotations

import io
import os
from pathlib import Path
import secrets
import stat
import tarfile


def profile_key(root: Path, site: str) -> bytes:
    folder = root / 'keys'
    if folder.is_symlink():
        raise ValueError('browser key directory must not be a symbolic link')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    path = folder / (site + '.key')
    if not path.exists() and not path.is_symlink():
        if (root / 'vaults' / (site + '.enc')).exists():
            raise ValueError('browser_key_missing: 请恢复 keys 与 vaults 的配套备份')
        key = secrets.token_bytes(32)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('browser key must be an owner-controlled regular file')
        os.fchmod(handle.fileno(), 0o600)
        key = handle.read(33)
    if len(key) != 32:
        raise ValueError('invalid browser key size')
    return key


class ProfileVault:
    def __init__(self, root: Path, site: str):
        self.root, self.site = Path(root), site
        folder = self.root / 'vaults'
        if folder.is_symlink():
            raise ValueError('browser vault must not be a symbolic link')
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
        self.path = folder / (site + '.enc')
        if self.path.is_symlink():
            raise ValueError('browser vault must not be a symbolic link')
        self.key = profile_key(self.root, site)

    def restore(self, destination: Path):
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.chmod(0o700)
        if not self.path.exists():
            return
        blob = self.path.read_bytes()
        try:
            if blob[:4] != b'SBV1':
                raise ValueError('unsupported browser vault version')
            raw = AESGCM(self.key).decrypt(blob[4:16], blob[16:], self.site.encode())
        except (InvalidTag, ValueError) as exc:
            raise ValueError('browser_vault_authentication_failed') from exc
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            for member in archive:
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('invalid browser vault member')
                member.mode = 0o700 if member.isdir() else 0o600
                archive.extract(member, destination, filter='data')

    def save(self, source: Path):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        data = io.BytesIO()
        def include(member):
            if not (member.isfile() or member.isdir()):
                return None
            if any(part in {'Cache', 'Code Cache', 'GPUCache', 'GrShaderCache', 'ShaderCache',
                            'DawnGraphiteCache', 'DawnWebGPUCache', 'Crashpad'} for part in Path(member.name).parts):
                return None
            if Path(member.name).name in {'DevToolsActivePort', 'SingletonCookie', 'SingletonLock', 'SingletonSocket'}:
                return None
            return member
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            archive.add(source, arcname='.', filter=include)
        nonce = secrets.token_bytes(12)
        blob = b'SBV1' + nonce + AESGCM(self.key).encrypt(nonce, data.getvalue(), self.site.encode())
        temporary = self.path.with_suffix('.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.path)
