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
        capture_output=True, text=True, cwd=HERE.parent,
    )
    if result.returncode != 0:
        pytest.fail(f"O programa Pulumi falhou no stack {stack}:\n{result.stderr[-3000:]}")
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


def test_openapi_documents_every_route():
    spec = yaml.safe_load((HERE.parent.parent / "docs" / "openapi.yaml").read_text())
    documented = {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations if method in ("get", "post", "put", "delete")
    }
    routes = {tuple(route.split(" ", 1)) for route in sam_routes()}
    for method, path in documented:
        assert (method, path) in routes or ("ANY", path) in routes, f"{method} {path} documentado sem rota"
    for method, path in routes:
        assert any(p == path and (method == "ANY" or m == method) for m, p in documented), f"{method} {path} sem documentação"


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
    functions = {f["name"]: f["inputs"] for f in of_type(stack, "aws:lambda/function:Function")}
    assert len(functions) == 9
    for name, fn in functions.items():
        assert fn["runtime"] == "python3.12"
        if name != "classly-login-audit":
            assert fn["environment"]["variables"]["ADMIN_EMAILS"] == "coordenacao@classly.test"
            assert fn["environment"]["variables"]["AUDIT_TABLE"] == "classly-audit"


def test_logins_are_audited_by_cognito_trigger(stack):
    pool = one(stack, "aws:cognito/userPool:UserPool")
    assert pool["lambdaConfig"]["postAuthentication"] == "arn:aws:mock:::classly-login-audit"
    permission = [p for p in of_type(stack, "aws:lambda/permission:Permission") if p["name"] == "classly-login-audit-cognito-permission"]
    assert permission[0]["inputs"]["principal"] == "cognito-idp.amazonaws.com"


def test_api_access_log_records_rejected_requests(stack):
    stage = one(stack, "aws:apigatewayv2/stage:Stage")
    log_format = json.loads(stage["accessLogSettings"]["format"])
    assert log_format["status"] == "$context.status"
    assert log_format["authorizerError"] == "$context.authorizer.error"


def test_budget_alert_only_in_prod():
    assert of_type("dev", "aws:budgets/budget:Budget") == []
    budget = one("prod", "aws:budgets/budget:Budget")
    assert (budget["limitAmount"], budget["timeUnit"]) == ("5", "MONTHLY")
    assert {n["threshold"] for n in budget["notifications"]} == {50, 80, 100}
    assert budget["notifications"][0]["subscriberEmailAddresses"] == ["coordenacao@classly.test"]


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
    assert objects["api-docs/openapi.yaml"]["contentType"] == "application/yaml"
    assert objects["api-docs/index.html"]["contentType"] == "text/html"

    config = json.loads(objects["config.json"]["content"])
    url = "https://classly.test" if stack == "prod" else "https://d111111abcdef8.cloudfront.net"
    assert config["apiBase"] == "/api"
    assert config["auth"]["redirectUri"] == f"{url}/"
    assert config["auth"]["clientId"] == "classly-web-id"
    assert config["googleClientId"] is None
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
    [zone] = of_type("prod", "aws:route53/zone:Zone")
    assert zone["inputs"]["name"] == "classly.test"

    records = {r["name"]: r["inputs"] for r in of_type("prod", "aws:route53/record:Record")}
    assert set(records) == {
        "classly-cert-validation", "classly-dkim-0", "classly-dkim-1", "classly-dkim-2",
        "classly-alias-a", "classly-alias-aaaa",
    }
    assert all(r["zoneId"] == "ZCLASSLY" for r in records.values())
    assert records["classly-dkim-0"]["name"] == "a1._domainkey.classly.test"

    certificate = [r for r in resources("prod") if r["type"] == "aws:acm/certificate:Certificate"][0]
    assert "pulumi:providers:aws::us-east-1::" in certificate["provider"]
    cdn = one("prod", "aws:cloudfront/distribution:Distribution")
    assert cdn["aliases"] == ["classly.test"]
    assert cdn["viewerCertificate"]["minimumProtocolVersion"] == "TLSv1.2_2021"


def test_prod_zone_is_protected_against_replacement():
    """Recriar a zona trocaria os NS e quebraria a delegação feita pelo professor."""
    source = (HERE.parent / "__main__.py").read_text()
    zone_block = source[source.index('aws.route53.Zone('):source.index("def dns_record")]
    assert "protect=True" in zone_block
