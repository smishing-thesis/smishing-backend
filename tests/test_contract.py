import json
from pathlib import Path

from smishing_backend.api.contracts import contract_app


def test_proposed_contract_snapshot():
    expected = json.loads(Path("docs/openapi-v1.json").read_text())
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
