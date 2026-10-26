"""Only launched by model_ui_check.cjs: explicit protocol simulation, never live AI."""
import json
import os

import httpx

from app.main import create_app
from app.planner import PlannerError, discover_models, local_plan, model_plan

MODEL_ID = "mock/vendor-complete-model-id-2026-10-26-protocol-only"


def upstream(request):
    if "FAKE_TEST_ONLY" not in request.headers.get("authorization", ""):
        return httpx.Response(401, json={"error":"This fixture accepts fake test keys only."})
    if request.method == "GET":
        return httpx.Response(200,json={"data":[{"id":MODEL_ID,"name":"协议模拟专用模型（非真实 AI）"}]})
    body=json.loads(request.content)
    if body["model"] != MODEL_ID:
        return httpx.Response(400,json={"error":"Selected model must be the simulated test ID."})
    context=json.loads(body["messages"][1]["content"])
    return httpx.Response(200,json={"model":MODEL_ID+"-response", "choices":[{"finish_reason":"stop","message":{"content":json.dumps(local_plan(context),ensure_ascii=False)}}]})


def discover(base, key):
    return discover_models(base,key,httpx.MockTransport(upstream))


# The production app's real adapter is exercised with an explicit mock transport.
def generate(context):
    config={"api_key":"FAKE_TEST_ONLY","base_url":"https://api.deepseek.com","model_id":MODEL_ID}
    return model_plan(context,transport=httpx.MockTransport(upstream),config=config)


if not os.environ.get("DATABASE_PATH") or "model-ui-fixture" not in os.environ["DATABASE_PATH"]:
    raise RuntimeError("This fixture requires a dedicated temporary test database.")
app=create_app(os.environ["DATABASE_PATH"],model_runner=generate,discovery_runner=discover)
