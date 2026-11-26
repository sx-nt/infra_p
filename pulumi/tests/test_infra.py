"""Testes da infraestrutura: o programa Pulumi roda com mocks, sem tocar na AWS."""

import json
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
SAM_TEMPLATE = HERE.parent.parent / "aws-sam" / "template.yaml"


@cache
def resources(stack):
    result = subprocess.run(
        [sys.executable, str(HERE / "harness.py"), stack],
        capture_output=True, text=True, check=True, cwd=HERE.parent,
    )
    payload = result.stdout[result.stdout.index("RESOURCES") + len("RESOURCES"):]
    return json.loads(payload)


def of_type(stack, type_):
    return [r for r in resources(stack) if r["type"] == type_]


def one(stack, type_):
    found = of_type(stack, type_)
    assert len(found) == 1, f"esperava 1 {type_}, encontrei {len(found)}"
    return found[0]["inputs"]


@pytest.fixture(params=["dev", "prod"])
def stack(request):
    return request.param


def sam_routes():
    class IgnoreTags(yaml.SafeLoader):
        pass

    IgnoreTags.add_multi_constructor("!", lambda loader, suffix, node: None)
    template = yaml.load(SAM_TEMPLATE.read_text(), Loader=IgnoreTags)
    return {
        f"{e['Properties']['Method'].upper()} {e['Properties']['Path']}"
        for r in template["Resources"].values() if r["Type"] == "AWS::Serverless::Function"
        for e in r["Properties"].get("Events", {}).values()
    }


def test_routes_match_local_sam_template(stack):
    routes = {r["inputs"]["routeKey"] for r in of_type(stack, "aws:apigatewayv2/route:Route")}
    assert routes == sam_routes()


def test_only_health_is_public(stack):
    for route in of_type(stack, "aws:apigatewayv2/route:Route"):
        expected = "NONE" if route["inputs"]["routeKey"] == "GET /health" else "JWT"
        assert route["inputs"]["authorizationType"] == expected, route["inputs"]["routeKey"]


def test_jwt_authorizer_trusts_only_the_user_pool_client(stack):
    authorizer = one(stack, "aws:apigatewayv2/authorizer:Authorizer")
    assert authorizer["authorizerType"] == "JWT"
    assert authorizer["jwtConfiguration"]["issuer"] == "https://cognito-idp.sa-east-1.amazonaws.com/sa-east-1_TEST"
    assert authorizer["jwtConfiguration"]["audiences"] == ["classly-web-id"]


def test_lambdas_use_python_and_shared_code(stack):
    functions = of_type(stack, "aws:lambda/function:Function")
    assert len(functions) == 8
    for fn in functions:
        assert fn["inputs"]["runtime"] == "python3.12"
        assert fn["inputs"]["environment"]["variables"]["ADMIN_EMAILS"] == "coordenacao@classly.test"


def test_lambda_permissions_are_scoped_to_tables(stack):
    for policy in of_type(stack, "aws:iam/rolePolicy:RolePolicy"):
        document = json.loads(policy["inputs"]["policy"])
        for statement in document["Statement"]:
            if statement["Action"] == "ses:SendEmail":
                assert policy["name"] == "classly-schedules-ses"
                continue
            assert all(arn.startswith("arn:aws:mock:::classly-") for arn in statement["Resource"])


def test_frontend_bucket_is_private_and_read_by_cloudfront_only(stack):
    block = one(stack, "aws:s3/bucketPublicAccessBlock:BucketPublicAccessBlock")
    assert all(block[k] for k in ("blockPublicAcls", "blockPublicPolicy", "ignorePublicAcls", "restrictPublicBuckets"))
    statement = json.loads(one(stack, "aws:s3/bucketPolicy:BucketPolicy")["policy"])["Statement"][0]
    assert statement["Principal"] == {"Service": "cloudfront.amazonaws.com"}
    assert statement["Action"] == "s3:GetObject"
    assert "AWS:SourceArn" in statement["Condition"]["StringEquals"]


def test_cloudfront_serves_site_and_api_over_https(stack):
    cdn = one(stack, "aws:cloudfront/distribution:Distribution")
    assert cdn["defaultRootObject"] == "index.html"
    assert cdn["defaultCacheBehavior"]["targetOriginId"] == "web"
    assert cdn["defaultCacheBehavior"]["viewerProtocolPolicy"] == "redirect-to-https"
    [api] = cdn["orderedCacheBehaviors"]
    assert api["pathPattern"] == "/api/*" and api["targetOriginId"] == "api"
    assert api["viewerProtocolPolicy"] == "redirect-to-https"
    assert api["functionAssociations"][0]["eventType"] == "viewer-request"


def test_cloudfront_function_strips_api_prefix():
    code = one("dev", "aws:cloudfront/function:Function")["code"]
    script = code + """
for (const uri of ['/api/teachers', '/api', '/api/schedules/1/publish', '/apix'])
  console.log(handler({ request: { uri } }).uri)
"""
    output = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout.split()
    assert output == ["/teachers", "/", "/schedules/1/publish", "/apix"]


def test_frontend_files_and_runtime_config_are_uploaded(stack):
    objects = {o["inputs"]["key"]: o["inputs"] for o in of_type(stack, "aws:s3/bucketObject:BucketObject")}
    assert objects["index.html"]["cacheControl"] == "no-cache"
    assert objects["index.html"]["contentType"] == "text/html"
    assets = [k for k in objects if k.startswith("assets/")]
    assert any(k.endswith(".js") for k in assets) and any(k.endswith(".css") for k in assets)
    assert all("immutable" in objects[k]["cacheControl"] for k in assets)

    config = json.loads(objects["config.json"]["content"])
    url = "https://classly.test" if stack == "prod" else "https://d111111abcdef8.cloudfront.net"
    assert config["apiBase"] == "/api"
    assert config["auth"]["redirectUri"] == f"{url}/"
    assert config["auth"]["clientId"] == "classly-web-id"
    assert re.fullmatch(rf"https://classly-{stack}-123456789012\.auth\.sa-east-1\.amazoncognito\.com", config["auth"]["domain"])


def test_cognito_verifies_email_and_uses_code_flow(stack):
    pool = one(stack, "aws:cognito/userPool:UserPool")
    assert pool["autoVerifiedAttributes"] == ["email"]
    assert pool["usernameAttributes"] == ["email"]
    assert pool["deletionProtection"] == ("ACTIVE" if stack == "prod" else "INACTIVE")
    client = one(stack, "aws:cognito/userPoolClient:UserPoolClient")
    assert client["allowedOauthFlows"] == ["code"]
    assert client["generateSecret"] is False


def test_dev_has_no_domain_resources():
    types = {r["type"] for r in resources("dev")}
    assert "aws:acm/certificate:Certificate" not in types
    assert "aws:route53/record:Record" not in types


def test_prod_publishes_domain_with_certificate_and_dkim():
    records = {r["name"]: r for r in of_type("prod", "aws:route53/record:Record")}
    assert set(records) == {
        "classly-cert-validation", "classly-dkim-0", "classly-dkim-1", "classly-dkim-2",
        "classly-alias-a", "classly-alias-aaaa",
    }
    shared_zone = [r for r in resources("prod") if r["name"] == "route53-shared-zone"][0]
    assert all("pulumi:providers:aws::route53-shared-zone::" in r["provider"] for r in records.values())
    # Entradas de provider chegam serializadas em JSON.
    assume_roles = json.loads(shared_zone["inputs"]["assumeRoles"])
    assert assume_roles[0]["externalId"] == "external-id"

    certificate = [r for r in resources("prod") if r["type"] == "aws:acm/certificate:Certificate"][0]
    assert "pulumi:providers:aws::us-east-1::" in certificate["provider"]
    cdn = one("prod", "aws:cloudfront/distribution:Distribution")
    assert cdn["aliases"] == ["classly.test"]
    assert cdn["viewerCertificate"]["minimumProtocolVersion"] == "TLSv1.2_2021"
