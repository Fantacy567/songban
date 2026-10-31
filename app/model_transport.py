"""Shared, retrying transport for OpenAI-compatible chat completions.

The team model endpoint (api.clawhunt.site, a doubao relay) is unreliable when
routed through the local HTTP proxy (127.0.0.1:7890 via trust_env=True): the
proxy intermittently resets the TLS connection, surfacing as
httpx.ConnectError. Direct connections (trust_env=False) are measurably more
stable, though they occasionally time out on connect/read. We therefore default
to bypassing the proxy and retry transient transport errors a few times.
"""
import time

import httpx

# Transient transport errors worth retrying once or twice. Pool/write timeouts
# are excluded: retrying those doubles latency for little gain, but connect and
# read timeouts are common on direct connections and safe to retry.
_TRANSIENT = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ProtocolError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
)


def post_chat_completion(base, api_key, body, timeout, attempts=3, follow_redirects=False, trust_env=False, transport=None):
    """POST a chat completion, retrying transient network errors.

    Returns the full httpx.Response. Non-transient errors (status codes,
    malformed responses, pool/write timeouts) are raised immediately and
    handled by callers.
    """
    url = base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + api_key}
    last = None
    for attempt in range(attempts):
        try:
            options = {'timeout': timeout, 'follow_redirects': follow_redirects, 'trust_env': trust_env}
            if transport is not None:
                options['transport'] = transport
            with httpx.Client(**options) as client:
                return client.post(url, headers=headers, json=body)
        except _TRANSIENT as exc:
            last = exc
            if attempt == attempts - 1:
                raise
            time.sleep(0.4 * (2 ** attempt))
    raise last  # pragma: no cover
