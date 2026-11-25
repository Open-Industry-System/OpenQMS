"""German/English response translation (app.i18n)."""

import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.i18n import pick_language, translate
from app.i18n.middleware import ResponseTranslationMiddleware


def test_pick_language():
    assert pick_language("de-DE,de;q=0.9,en;q=0.8") == "de"
    assert pick_language("en-US") == "en"
    assert pick_language("zh-CN") is None
    assert pick_language(None) is None


def test_translate_exact_and_pattern():
    assert translate("供应商不存在", "de") == "Lieferant existiert nicht"
    assert translate("供应商不存在", "en") == "Supplier does not exist"
    assert translate("产品线 'DC-DC-100' 不存在", "de") == "Produktlinie 'DC-DC-100' existiert nicht"
    # reordered placeholders
    assert translate("需要 spc 模块的 EDIT 权限", "de") == "EDIT-Berechtigung für das Modul spc erforderlich"
    # nested message
    assert translate("文档门禁未通过：文档已变更，请重新审核", "en") == "Document gate not passed: Document changed, please re-audit"


def test_translate_leaves_data_values_and_unknown_text():
    for value in ("一般", "致命", "符合", "随便写的文字"):
        assert translate(value, "de") == value
    assert translate("供应商不存在", None) == "供应商不存在"


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ResponseTranslationMiddleware)

    @app.get("/err")
    def err():
        raise HTTPException(status_code=404, detail="供应商不存在")

    @app.get("/data")
    def data():
        return {"severity": "一般", "items": [{"label": "质量分"}]}

    @app.get("/text")
    def text():
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse("供应商不存在")

    return app


def test_middleware_translates_json_per_accept_language():
    client = TestClient(_app())
    assert client.get("/err").json() == {"detail": "供应商不存在"}
    assert client.get("/err", headers={"Accept-Language": "de-DE"}).json() == {"detail": "Lieferant existiert nicht"}
    assert client.get("/err", headers={"Accept-Language": "en-US"}).json() == {"detail": "Supplier does not exist"}

    resp = client.get("/data", headers={"Accept-Language": "de-DE"})
    assert resp.json() == {"severity": "一般", "items": [{"label": "Qualitätsbewertung"}]}
    assert int(resp.headers["content-length"]) == len(resp.content)
    json.loads(resp.content)

    assert client.get("/text", headers={"Accept-Language": "de-DE"}).text == "供应商不存在"
