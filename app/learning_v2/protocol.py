"""Strict validation of the frozen P1 JSON Schema subset; no request values in errors."""
import json
import math
import re
from datetime import datetime
from pathlib import Path


class Problem(Exception):
    def __init__(self, status, code, message, recovery="none", revision=None):
        self.status, self.code, self.message = status, code, message
        self.recovery, self.revision = recovery, revision

    def payload(self):
        return {"error": {"code": self.code, "message": self.message,
                          "retryable": self.status in (429, 503), "recovery": self.recovery,
                          "current_revision": self.revision}}


def fail(status, code, message, recovery="none", revision=None):
    raise Problem(status, code, message, recovery, revision)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("non-finite number")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        canonical(value).encode("utf-8")  # Also reject overflow-to-infinity and lone surrogates.
        return value
    except (ValueError, UnicodeError, RecursionError):
        fail(422, "invalid_input", "请求格式不正确。")


class Contract:
    def __init__(self):
        self.document = json.loads(Path(__file__).with_name("contract.json").read_text(encoding="utf-8"))
        self.schemas = self.document["components"]["schemas"]

    def valid(self, value, schema):
        if "$ref" in schema:
            return self.valid(value, self.schemas[schema["$ref"].rsplit("/", 1)[-1]])
        if "oneOf" in schema and sum(self.valid(value, s) for s in schema["oneOf"]) != 1:
            return False
        if "anyOf" in schema and not any(self.valid(value, s) for s in schema["anyOf"]):
            return False
        if "allOf" in schema and not all(self.valid(value, s) for s in schema["allOf"]):
            return False
        if "if" in schema and self.valid(value, schema["if"]) and not self.valid(value, schema.get("then", {})):
            return False
        if "if" in schema and not self.valid(value, schema["if"]) and not self.valid(value, schema.get("else", {})):
            return False
        types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
        if schema.get("type") == "number":
            if type(value) not in (int, float) or not math.isfinite(value):
                return False
        elif "type" in schema and type(value) is not types[schema["type"]]:
            return False
        if "enum" in schema and value not in schema["enum"]:
            return False
        if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
            return False
        if isinstance(value, dict):
            props = schema.get("properties", {})
            if any(k not in value for k in schema.get("required", [])):
                return False
            if schema.get("additionalProperties") is False and any(k not in props for k in value):
                return False
            if not schema.get("minProperties", 0) <= len(value) <= schema.get("maxProperties", float("inf")):
                return False
            if any(not self.valid(v, props[k]) for k, v in value.items() if k in props):
                return False
        if isinstance(value, list):
            if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", float("inf")):
                return False
            if "items" in schema and not all(self.valid(v, schema["items"]) for v in value):
                return False
            if schema.get("uniqueItems") and len({canonical(v) for v in value}) != len(value):
                return False
            if "contains" in schema:
                count = sum(self.valid(v, schema["contains"]) for v in value)
                if not schema.get("minContains", 1) <= count <= schema.get("maxContains", float("inf")):
                    return False
        if isinstance(value, str):
            if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", float("inf")):
                return False
            if "pattern" in schema and not re.search(schema["pattern"], value):
                return False
            if schema.get("format") == "date-time":
                try:
                    if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                        return False
                except ValueError:
                    return False
        if type(value) in (int, float) and not schema.get("minimum", -float("inf")) <= value <= schema.get("maximum", float("inf")):
            return False
        return True

    def check(self, value, schema):
        if not self.valid(value, schema):
            fail(422, "invalid_input", "字段、类型或答案状态不符合当前接口。")


def revision(expected, actual):
    if expected != actual:
        fail(409, "revision_conflict", "记录已更新，请保留输入并读取最新版本。", "merge", actual)
