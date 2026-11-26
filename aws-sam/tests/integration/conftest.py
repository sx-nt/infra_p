import importlib
import os
import re
from pathlib import Path

import boto3
import pytest
import yaml

from support import COORDINATOR, call, create_tables

TEMPLATE = Path(__file__).parents[2] / "template.yaml"


class _IgnoreTags(yaml.SafeLoader):
    """Lê o template SAM ignorando tags do CloudFormation (!Ref, !Sub...)."""


_IgnoreTags.add_multi_constructor("!", lambda loader, suffix, node: None)


def _routes():
    """(método, regex da rota, handler) para cada evento Api do template SAM."""
    resources = yaml.load(TEMPLATE.read_text(), Loader=_IgnoreTags)["Resources"]
    routes = []
    for resource in resources.values():
        if resource["Type"] != "AWS::Serverless::Function":
            continue
        module_name, function_name = resource["Properties"]["Handler"].rsplit(".", 1)
        handler = getattr(importlib.import_module(module_name), function_name)
        for event in resource["Properties"].get("Events", {}).values():
            props = event["Properties"]
            pattern = "^" + re.sub(r"\{[^/]+\}", "[^/]+", props["Path"]) + "$"
            routes.append((props["Method"].upper(), re.compile(pattern), handler))
    return routes


ROUTES = _routes()


def route(method, path):
    """Escolhe a função como o API Gateway: rota exata e método (ou ANY)."""
    for route_method, pattern, handler in ROUTES:
        if pattern.match(path) and route_method in (method, "ANY"):
            return handler
    return None


@pytest.fixture(scope="session")
def dynamodb():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT")
    if not endpoint:
        pytest.skip("Defina DYNAMODB_ENDPOINT (ex.: http://localhost:8000) com o DynamoDB Local no ar.")
    return boto3.resource("dynamodb", region_name="us-east-1", endpoint_url=endpoint)


@pytest.fixture
def api(dynamodb):
    create_tables(dynamodb)

    def request(method, path, body=None, email=COORDINATOR):
        handler = route(method, path)
        if handler is None:
            return 404, {"message": "Sem rota no API Gateway."}
        return call(handler, method, path, body, email)

    return request
