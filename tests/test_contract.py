import json
from pathlib import Path

from smishing_backend.api.contracts import contract_app


def test_proposed_contract_snapshot():
    expected = json.loads(Path("docs/openapi-v1.json").read_text(encoding="utf-8"))
    assert contract_app().openapi() == expected
    schema = expected["components"]["schemas"]["ContributionInput"]
    assert set(schema["properties"]) == {"text", "label", "model_version"}
    assert schema["additionalProperties"] is False
    assert set(expected["paths"]["/api/v1/contributions"]["post"]["responses"]) == {
        "201",
        "400",
        "401",
        "409",
        "413",
        "422",
        "429",
        "503",
    }


def test_batch_contract():
    expected = json.loads(Path("docs/openapi-v1.json").read_text(encoding="utf-8"))
    schemas = expected["components"]["schemas"]
    assert set(schemas["ContributionResult"]["properties"]) == {
        "index",
        "status",
        "reason",
    }
    assert set(schemas["ContributionResult"]["required"]) == {"index", "status"}
    assert schemas["ContributionBatchInput"]["additionalProperties"] is False
    operation = expected["paths"]["/api/v1/contributions/batch"]["post"]
    assert set(operation["responses"]) == {
        "200",
        "400",
        "401",
        "413",
        "422",
        "429",
        "503",
    }
    assert "Retry-After" in operation["responses"]["429"]["headers"]
    assert expected["info"]["version"] == "1.1.0"
