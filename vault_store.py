"""Optional Vaultwarden backend: store and read secrets in a Bitwarden-compatible vault.

The default store stays the profile env file (see ``secret_drop.py``). When
``secret_drop.backend`` is ``vaultwarden`` in the Hermes config, a stored secret
becomes a login item in the vault and the alias resolves the value from there.

Why a native client instead of ``bw``/``rbw``: the alias hook runs on every tool
call, so a process start per lookup is too expensive, and no extra binary has to
be installed. The protocol is small - token login, ``/api/sync``, ``/api/ciphers``
- and the crypto is PBKDF2 + AES-CBC + HMAC, which ``cryptography`` already
provides on this runtime.

Configuration (``~/.hermes/config.yaml``)::

    secret_drop:
      backend: vaultwarden          # default: file
      vaultwarden:
        base_url: https://vault.example.test
        email_env: VAULT_EMAIL      # name of the stored secret holding the login
        password_env: VAULT_PASSWORD
        timeout: 20
        cache_seconds: 15

The login values are read from the profile environment file by this module
itself; they never pass through a tool argument or a log line.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_PLUGIN_ID = "secret-drop"
# Names the manifest's ``config_schema`` declares for the two secret fields, so the
# Desktop plugins hub writes them into the same place this module reads. Both are
# credential-shaped on purpose: core's redaction and this plugin's own credential
# filter match ``*_PASSWORD`` / ``*_USER`` names, so the master password becomes a
# scrubbing needle the moment it is stored. The 1.7.0 names (``vaultwarden`` /
# ``vaultwarden_USER``) matched no filter and leaked through ``echo $vaultwarden``.
_EMAIL_ENV = "VAULTWARDEN_USER"
_PASSWORD_ENV = "VAULTWARDEN_PASSWORD"
# Names versions 1.7.0/1.7.1 wrote the login under. Nothing scrubbed them, so they
# are migrated to the names above once per session start (see
# ``migrate_legacy_login_names``) and never read as a primary source.
_LEGACY_EMAIL_ENV = "vaultwarden_USER"
_LEGACY_PASSWORD_ENV = "vaultwarden"
_BACKEND_FILE = "file"
_BACKEND_VAULT = "vaultwarden"
_DEFAULT_CACHE_SECONDS = 15.0
_DEFAULT_TIMEOUT = 20.0
_CLIENT_ID = "cli"
_ITEM_TYPE_LOGIN = 1


class VaultError(RuntimeError):
    """A refusal whose message is safe to show to the user (no value, no token)."""


class VaultAuthError(VaultError):
    """A 401 from the vault: the stored token expired. Callers re-log in once."""


class _SameHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when it stays on the configured host and scheme.

    urllib's default handler copies ``Authorization: Bearer`` to the redirect
    target, so a redirect off the configured host would hand the token to
    another server. Raising here stops the redirect before any request is made.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlparse(req.full_url)
        new = urllib.parse.urlparse(newurl)
        if (
            (new.hostname or "").lower() != (old.hostname or "").lower()
            or new.scheme != old.scheme
        ):
            raise urllib.error.HTTPError(
                newurl, code, "refusing a redirect off the configured host", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_SAFE_OPENER = urllib.request.build_opener(_SameHostRedirectHandler())


# --------------------------------------------------------------------------- config


def _settings_map() -> dict:
    """``plugins.entries.<id>.settings`` - the block the plugins hub writes to."""
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly()
    except Exception as exc:  # a gateway that cannot read its config must say so
        logger.warning("vaultwarden: config not readable, staying on the file backend (%s)", exc)
        return {}
    entries = ((config or {}).get("plugins") or {}).get("entries") or {}
    entry = entries.get(_PLUGIN_ID) or {}
    settings = entry.get("settings") if isinstance(entry, dict) else None
    return settings if isinstance(settings, dict) else {}


def _setting(key: str, default=None):
    return _settings_map().get(key, default)


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _validated_base_url(url: str) -> str:
    """Refuse a base URL that would carry the master-password hash or the bearer
    token in clear, or to a host that is not the configured one.

    ``http://`` is accepted only for a loopback host; anything else must be
    ``https://``. Callers raise before any request is made, so a misconfigured
    URL fails loudly instead of downgrading the transport.
    """
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise VaultError("the vault URL carries no host")
    if parsed.scheme == "https":
        return url
    if parsed.scheme == "http" and (
        host in _LOOPBACK_HOSTS or host.startswith("127.")
    ):
        return url
    raise VaultError(
        "the vault URL must use https; http is only allowed for a loopback host"
    )


def backend() -> str:
    """Active secret store backend. Anything but an explicit vault config is ``file``.

    An explicit vault config with a non-https, non-loopback URL raises
    :class:`VaultError` instead of falling back to the file store silently: a
    secret that was meant for the vault must not land in the environment file
    because the URL was misconfigured.
    """
    if str(_setting("backend") or _BACKEND_FILE).strip().lower() != _BACKEND_VAULT:
        return _BACKEND_FILE
    raw_url = str(_setting("vaultwarden_base_url") or "").strip()
    if not raw_url:
        logger.warning("vaultwarden backend selected without a URL; using the file store")
        return _BACKEND_FILE
    _validated_base_url(raw_url)
    return _BACKEND_VAULT


def migrate_legacy_login_names() -> None:
    """Move login values stored under the 1.7.0/1.7.1 names to the credential-shaped names.

    Versions before 1.7.2 wrote the vault login into the profile environment
    file as ``vaultwarden`` and ``vaultwarden_USER``. Neither name matches the
    credential filters, so the master password was not a scrubbing needle. The
    migration runs once per session start; the new name wins when both exist,
    and the legacy entry is removed in every case.
    """
    try:
        from hermes_cli.config import load_env, remove_env_value, save_env_value_secure
    except Exception as exc:  # a gateway that cannot rewrite its env stays on old names
        logger.warning("vaultwarden: login migration unavailable (%s)", exc)
        return
    try:
        env = load_env()
    except Exception as exc:
        logger.warning("vaultwarden: login migration could not read the environment (%s)", exc)
        return
    if not isinstance(env, dict):
        return
    for legacy, current in (
        (_LEGACY_PASSWORD_ENV, _PASSWORD_ENV),
        (_LEGACY_EMAIL_ENV, _EMAIL_ENV),
    ):
        value = env.get(legacy)
        if not isinstance(value, str) or not value:
            continue
        try:
            if not env.get(current):
                save_env_value_secure(current, value)
            remove_env_value(legacy)
        except Exception as exc:
            logger.warning(
                "vaultwarden: could not migrate the legacy login name %s (%s)", legacy, exc
            )


def uses_vault() -> bool:
    return backend() == _BACKEND_VAULT


def _settings() -> dict:
    return {
        "base_url": str(_setting("vaultwarden_base_url") or "").strip(),
        "timeout": _DEFAULT_TIMEOUT,
        "cache_seconds": _DEFAULT_CACHE_SECONDS,
    }


def _env_secret(name: str, legacy: str | None = None) -> str:
    """Credential behind *name*: profile-scoped first, then the profile environment file.

    ``get_secret`` reads the process environment, which only sees a value stored after
    the gateway started once the gateway restarts; the file is where this plugin writes
    it, so it is the second source. Neither path returns the value to a tool caller.

    *legacy* is the pre-1.7.2 spelling of the same credential. It is only consulted
    when the current name holds nothing, so a running gateway that still carries the
    old name keeps working until the migration below moves it.
    """
    value = None
    try:
        from agent.secret_scope import get_secret

        value = get_secret(name)
    except Exception:
        logger.debug("vaultwarden: profile-scoped secret lookup unavailable", exc_info=True)
    if isinstance(value, str) and value:
        return value
    if legacy:
        try:
            from agent.secret_scope import get_secret

            value = get_secret(legacy)
        except Exception:
            value = None
        if isinstance(value, str) and value:
            return value
    from hermes_cli.config import load_env

    env = load_env()
    if not isinstance(env, dict):
        return ""
    for key in (name, legacy) if legacy else (name,):
        found = env.get(key)
        if isinstance(found, str) and found:
            return found
    return ""


def _has_legacy_login() -> bool:
    """Whether the profile environment still carries a pre-1.7.2 login name."""
    try:
        from hermes_cli.config import load_env

        env = load_env()
    except Exception:
        return False
    if not isinstance(env, dict):
        return False
    return bool(env.get(_LEGACY_PASSWORD_ENV) or env.get(_LEGACY_EMAIL_ENV))


_LEGACY_MIGRATION_TRIED = False


def _login_values() -> tuple[str, str]:
    global _LEGACY_MIGRATION_TRIED
    # The old spelling is the fallback source, not only a migration trigger: a
    # gateway that was running under 1.7.0/1.7.1 must keep resolving aliases
    # until the migration has rewritten the profile environment.
    email = _env_secret(_EMAIL_ENV, _LEGACY_EMAIL_ENV)
    password = _env_secret(_PASSWORD_ENV, _LEGACY_PASSWORD_ENV)
    if not _LEGACY_MIGRATION_TRIED and _has_legacy_login():
        _LEGACY_MIGRATION_TRIED = True
        migrate_legacy_login_names()
    if not email or not password:
        raise VaultError("the vault login is not available")
    return email, password


# --------------------------------------------------------------------------- crypto


def _b64decode(text: str) -> bytes:
    return base64.b64decode(text + "=" * (-len(text) % 4))


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-Expand without Extract - what Bitwarden clients use for ``stretchKey``."""
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _stretch(master_key: bytes) -> tuple[bytes, bytes]:
    return _hkdf_expand(master_key, b"enc"), _hkdf_expand(master_key, b"mac")


def _decrypt(enc_string: str, enc_key: bytes, mac_key: bytes) -> bytes:
    """Decrypt a type-2 EncString (``2.iv|ct|mac``)."""
    if not isinstance(enc_string, str) or enc_string.count(".") != 1:
        raise VaultError("unexpected vault item encoding")
    kind, payload = enc_string.split(".", 1)
    if kind != "2":
        raise VaultError("unexpected vault item encoding")
    try:
        iv_b64, ct_b64, mac_b64 = payload.split("|")
    except ValueError as exc:
        raise VaultError("unexpected vault item encoding") from exc
    iv, cipher_text, mac = _b64decode(iv_b64), _b64decode(ct_b64), _b64decode(mac_b64)
    expected = hmac.new(mac_key, iv + cipher_text, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, mac):
        raise VaultError("vault item could not be verified")
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    decryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(cipher_text) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _encrypt(plain: str, enc_key: bytes, mac_key: bytes) -> str:
    import os

    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plain.encode()) + padder.finalize()
    iv = os.urandom(16)
    encryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).encryptor()
    cipher_text = encryptor.update(padded) + encryptor.finalize()
    mac = hmac.new(mac_key, iv + cipher_text, hashlib.sha256).digest()
    return "2." + "|".join(_b64encode(part) for part in (iv, cipher_text, mac))


# --------------------------------------------------------------------------- client


class VaultClient:
    """Minimal Bitwarden/Vaultwarden client for login items."""

    def __init__(
        self,
        base_url: str,
        email: str,
        password: str,
        timeout: float,
        cache_seconds: float = _DEFAULT_CACHE_SECONDS,
    ) -> None:
        self._base = _validated_base_url(base_url).rstrip("/")
        self._email = email
        self._password = password
        self._timeout = float(timeout)
        self._cache_seconds = float(cache_seconds)
        self._token = ""
        self._enc_key = b""
        self._mac_key = b""
        self._user_id = ""
        self._lock = threading.RLock()
        self._items_cache: list[dict] | None = None
        self._items_time = 0.0

    # -- transport

    def _request(self, path: str, method: str = "GET", payload=None, form=None, auth: bool = True):
        url = self._base + path
        headers = {"Accept": "application/json"}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if auth and self._token:
            headers["Authorization"] = "Bearer " + self._token
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with _SAFE_OPENER.open(request, timeout=self._timeout) as response:
                raw = response.read().decode()
                return response.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            if exc.code == 401:
                self._token = ""
                raise VaultAuthError("the vault refused the login") from None
            detail = ""
            try:
                body = json.loads(raw)
                detail = json.dumps(
                    {
                        k: body.get(k)
                        for k in ("message", "error", "error_description", "validationErrors", "errorModel")
                        if body.get(k)
                    }
                )[:400]
            except Exception:
                detail = raw[:400]
            logger.warning("vaultwarden answered %s on %s: %s", exc.code, path, detail)
            raise VaultError("the vault answered %s" % exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("vaultwarden transport failed: %s", type(exc).__name__)
            raise VaultError("the vault is not reachable") from None

    # -- session

    def _prelogin_iterations(self) -> int:
        status, body = self._request(
            "/identity/accounts/prelogin",
            method="POST",
            payload={"email": self._email},
            auth=False,
        )
        iterations = 600_000
        if isinstance(body, dict):
            try:
                iterations = int(body.get("kdfIterations") or iterations)
            except (TypeError, ValueError):
                iterations = 600_000
        return max(iterations, 1)

    def login(self) -> None:
        """Derive the keys, log in, and unwrap the user key. Idempotent."""
        with self._lock:
            iterations = self._prelogin_iterations()
            master_key = hashlib.pbkdf2_hmac(
                "sha256", self._password.encode(), self._email.lower().encode(), iterations, 32
            )
            master_hash = _b64encode(hashlib.pbkdf2_hmac("sha256", master_key, self._password.encode(), 1, 32))
            status, body = self._request(
                "/identity/connect/token",
                method="POST",
                form={
                    "grant_type": "password",
                    "username": self._email,
                    "password": master_hash,
                    "scope": "api offline_access",
                    "client_id": _CLIENT_ID,
                    "deviceType": "10",
                    "deviceIdentifier": "hermes-secret-drop",
                    "deviceName": "hermes-secret-drop",
                },
                auth=False,
            )
            token = (body or {}).get("access_token") if isinstance(body, dict) else None
            if not token:
                raise VaultError("the vault refused the login")
            self._token = token
            enc_key, mac_key = _stretch(master_key)
            status, profile = self._request("/api/accounts/profile")
            wrapped = (profile or {}).get("key") if isinstance(profile, dict) else None
            user_id = (profile or {}).get("id") if isinstance(profile, dict) else None
            if not user_id:
                raise VaultError("the vault profile carries no account id")
            self._user_id = str(user_id)
            if wrapped:
                raw = _decrypt(wrapped, enc_key, mac_key)
                if len(raw) != 64:
                    raw = _b64decode(raw.decode())
                if len(raw) != 64:
                    raise VaultError("unexpected vault key material")
                enc_key, mac_key = raw[:32], raw[32:]
            self._enc_key, self._mac_key = enc_key, mac_key

    def _ensure_session(self) -> None:
        if not self._token:
            self.login()

    # -- items

    @staticmethod
    def _item_keys(cipher: dict, enc_key: bytes, mac_key: bytes) -> tuple[bytes, bytes]:
        wrapped = cipher.get("key")
        if not wrapped:
            return enc_key, mac_key
        raw = _decrypt(wrapped, enc_key, mac_key)
        if len(raw) != 64:
            raw = _b64decode(raw.decode())
        if len(raw) != 64:
            raise VaultError("unexpected vault item key")
        return raw[:32], raw[32:]

    def items(self) -> list[dict]:
        """Every login item as ``{"name", "password", "username", "id"}`` (plain values).

        The item list is cached for ``cache_seconds``, so a tool-output scrub
        over many stored names performs one ``/api/sync`` instead of one per
        name. A 401 (expired token) re-logs in exactly once and retries; any
        other failure propagates.
        """
        with self._lock:
            now = time.monotonic()
            if self._items_cache is not None and now - self._items_time < self._cache_seconds:
                return self._items_cache
            self._ensure_session()
            try:
                result = self._fetch_items()
            except VaultAuthError:
                self.login()
                result = self._fetch_items()
            self._items_cache = result
            self._items_time = now
            return result

    def _fetch_items(self) -> list[dict]:
        with self._lock:
            status, sync = self._request("/api/sync")
            ciphers = (sync or {}).get("ciphers") if isinstance(sync, dict) else None
            if ciphers is None:
                raise VaultError("the vault returned no items")
            result = []
            for cipher in ciphers:
                if cipher.get("type") != _ITEM_TYPE_LOGIN:
                    continue
                try:
                    item_enc, item_mac = self._item_keys(cipher, self._enc_key, self._mac_key)
                    name = _decrypt(cipher["name"], item_enc, item_mac).decode()
                except (VaultError, KeyError, UnicodeDecodeError):
                    continue
                login = cipher.get("login") or {}
                entry = {"id": cipher.get("id"), "name": name, "password": "", "username": ""}
                if login.get("password"):
                    try:
                        entry["password"] = _decrypt(login["password"], item_enc, item_mac).decode()
                    except (VaultError, UnicodeDecodeError):
                        entry["password"] = ""
                if login.get("username"):
                    try:
                        entry["username"] = _decrypt(login["username"], item_enc, item_mac).decode()
                    except (VaultError, UnicodeDecodeError):
                        entry["username"] = ""
                result.append(entry)
            return result

    def put_item(self, name: str, value: str, username: str | None = None) -> str:
        """Create or update the login item called *name*. Returns ``created``/``updated``."""
        with self._lock:
            self._ensure_session()
            existing = next((item for item in self.items() if item["name"] == name), None)
            login = {
                "password": _encrypt(value, self._enc_key, self._mac_key),
                "uris": [],
            }
            if username:
                login["username"] = _encrypt(username, self._enc_key, self._mac_key)
            payload = {
                "type": _ITEM_TYPE_LOGIN,
                "name": _encrypt(name, self._enc_key, self._mac_key),
                "encryptedFor": self._user_id,
                "favorite": False,
                "login": login,
                "fields": [],
            }
            if existing and existing.get("id"):
                payload["id"] = existing["id"]
                self._request("/api/ciphers/" + str(existing["id"]), method="PUT", payload=payload)
                self._items_cache = None
                return "updated"
            self._request("/api/ciphers", method="POST", payload=payload)
            self._items_cache = None
            return "created"


# --------------------------------------------------------------------------- cache


_CACHE: dict[tuple[str, str], tuple[float, VaultClient]] = {}
_CACHE_LOCK = threading.RLock()


def _client(settings: dict) -> VaultClient:
    email, password = _login_values()
    base_url = _validated_base_url(str(settings.get("base_url") or "").rstrip("/"))
    key = (base_url, email)
    cache_seconds = float(settings.get("cache_seconds") or _DEFAULT_CACHE_SECONDS)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        # The session survives: the client is only rebuilt when the login values
        # change. An expired token re-logs in on its own (items() on 401), so
        # the 600k-iteration PBKDF2 no longer runs once per cache TTL.
        if cached and cached[1]._password == password:
            return cached[1]
        client = VaultClient(
            base_url,
            email,
            password,
            settings.get("timeout") or _DEFAULT_TIMEOUT,
            cache_seconds,
        )
        _CACHE[key] = (time.monotonic(), client)
        return client


def lookup(name: str) -> str | None:
    """Password for the item called *name*, or ``None`` when no such item exists.

    Raises :class:`VaultError` when the vault is configured but unreachable - a
    missing item is not a reason to fall back to another store silently, an
    unreachable vault has to be visible to the caller.
    """
    if not uses_vault():
        return None
    settings = _settings()
    client = _client(settings)
    for item in client.items():
        if item["name"] == name:
            return item["password"]
        if item["name"].lower() == name.lower():
            return item["password"]
    return None


def store(name: str, value: str, username: str | None = None) -> str:
    """Write *value* into the vault as login item *name*. Returns ``created``/``updated``."""
    if not uses_vault():
        raise VaultError("the vaultwarden backend is not configured")
    settings = _settings()
    client = _client(settings)
    # Do NOT drop the client cache here: a fresh client would have to log in
    # again, which turned a 23-secret migration into 23 logins and tripped
    # the rate limiter. put_item() invalidates the cached item list itself, so
    # a stale list cannot happen.
    return client.put_item(name, value, username)


def username_for(name: str) -> str | None:
    """Username stored beside item *name*, or ``None``."""
    if not uses_vault():
        return None
    settings = _settings()
    client = _client(settings)
    best = None
    for item in client.items():
        if item["name"] == name:
            return item["username"] or None
        if item["name"].lower() == name.lower() and best is None:
            best = item["username"] or None
    return best
