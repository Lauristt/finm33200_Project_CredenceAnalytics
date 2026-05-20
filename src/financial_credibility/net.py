from __future__ import annotations

import ssl
import urllib.error
import urllib.request


def urlopen_request(
    request: urllib.request.Request,
    timeout: float,
    allow_insecure_ssl_fallback: bool = False,
):
    context = _verified_context()
    try:
        return urllib.request.urlopen(request, timeout=timeout, context=context)
    except urllib.error.URLError as exc:
        if allow_insecure_ssl_fallback and _is_ssl_verify_error(exc):
            insecure_context = ssl._create_unverified_context()
            return urllib.request.urlopen(
                request,
                timeout=timeout,
                context=insecure_context,
            )
        raise


def _verified_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _is_ssl_verify_error(exc: urllib.error.URLError) -> bool:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)
