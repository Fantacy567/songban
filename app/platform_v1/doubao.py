"""Bounded single-image Ark adapter. Explicit server model; no ambient secrets.

Verified against https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh
on 2026-11-02. Provider requests are never retried by this adapter. Protocol
fixtures use injected httpx transport and are labelled separately from Doubao.
"""
import base64
import binascii
from dataclasses import dataclass, field
from io import BytesIO
import warnings

import httpx
from PIL import Image, UnidentifiedImageError


ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"


class ProviderUnknown(Exception):
    """Dispatch occurred; completion/usage cannot safely be inferred."""


class ProviderRejected(Exception):
    """A definite pre-generation rejection, without returning provider text."""


@dataclass(frozen=True)
class ImageResult:
    content: bytes = field(repr=False)
    actual_model: str | None = None
    provider_request_id: str | None = None
    source: str = "doubao"
    generated_images: int | None = None


def inspect_image(content, *, max_bytes=12582912, max_pixels=16777216):
    if not isinstance(content, bytes) or not 0 < len(content) <= max_bytes:
        raise ValueError("Invalid image size")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                fmt, width, height = image.format, image.width, image.height
                if fmt not in ("PNG", "JPEG", "WEBP") or not (0 < width <= 8192 and 0 < height <= 8192) or width * height > max_pixels:
                    raise ValueError("Unsupported image")
                if getattr(image, "is_animated", False):
                    raise ValueError("Animated image not supported")
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, ValueError):
        raise ValueError("Invalid image") from None
    return {"mime": {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt],
            "extension": {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt],
            "width": width, "height": height, "byte_size": len(content)}


class DoubaoAdapter:
    def __init__(self, config):
        self.config = config

    def generate(self, prompt):
        cfg = self.config
        if not cfg.api_key or not cfg.model:
            raise ProviderRejected("Image provider is unconfigured")
        payload = {"model": cfg.model, "prompt": prompt, "size": cfg.size,
                   "response_format": "b64_json", "stream": False, "watermark": True}
        # 5.0 pro/flash do not accept the sequential parameter. Capability is
        # explicit server configuration; endpoint/model names are not guessed.
        if cfg.supports_sequential_generation:
            payload["sequential_image_generation"] = "disabled"
        max_json = cfg.max_bytes * 4 // 3 + 131072
        try:
            with httpx.Client(transport=cfg.transport, trust_env=False, follow_redirects=False,
                              timeout=cfg.timeout_seconds) as client:
                with client.stream("POST", ENDPOINT, headers={"Authorization": "Bearer " + cfg.api_key,
                                   "Content-Type": "application/json"}, json=payload) as response:
                    if response.status_code in (400, 401, 403, 404, 413, 422, 429):
                        raise ProviderRejected("Image generation rejected")
                    if response.status_code != 200:
                        raise ProviderUnknown("Image completion unknown")
                    raw = bytearray()
                    for part in response.iter_bytes():
                        raw.extend(part)
                        if len(raw) > max_json:
                            raise ProviderUnknown("Image response exceeds limit")
                    import json
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ProviderUnknown("Image response invalid")
                    model = value.get("model")
                    if not isinstance(model, str) or model not in (cfg.model, *cfg.allowed_response_models):
                        raise ProviderUnknown("Unexpected response model")
                    data = value.get("data")
                    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict) or data[0].get("error"):
                        raise ProviderUnknown("Single image completion unconfirmed")
                    encoded = data[0].get("b64_json")
                    if not isinstance(encoded, str) or len(encoded) > cfg.max_bytes * 4 // 3 + 8:
                        raise ProviderUnknown("Image bytes unavailable")
                    content = base64.b64decode(encoded, validate=True)
                    inspect_image(content, max_bytes=cfg.max_bytes, max_pixels=cfg.max_pixels)
                    usage = value.get("usage", {})
                    count = usage.get("generated_images") if isinstance(usage, dict) else None
                    if count is not None and (type(count) is not int or count != 1):
                        raise ProviderUnknown("Image usage inconsistent")
                    request_id = response.headers.get("x-request-id")
                    if request_id and (len(request_id) > 200 or not request_id.isascii() or any(ord(c) < 33 for c in request_id)):
                        request_id = None
                    return ImageResult(content, model, request_id,
                                       "test_fixture" if isinstance(cfg.transport, httpx.MockTransport) else "doubao", count)
        except (ProviderRejected, ProviderUnknown):
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError, binascii.Error, UnicodeError):
            # Never include response, request headers, URL parameters or secrets.
            raise ProviderUnknown("Image completion unknown") from None
