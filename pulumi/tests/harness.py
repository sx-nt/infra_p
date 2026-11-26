"""Executa o programa Pulumi com mocks e imprime os recursos registrados (JSON).

Uso: python tests/harness.py <stack>. Roda em processo separado porque o
runtime do Pulumi guarda estado global por execução.
"""

import json
import runpy
import sys
import time
from pathlib import Path

import pulumi

STACK = sys.argv[1]
PROGRAM_DIR = Path(__file__).resolve().parent.parent
resources = []


class Mocks(pulumi.runtime.Mocks):
    def new_resource(self, args):
        outputs = dict(args.inputs)
        fake = {
            "aws:apigatewayv2/api:Api": {
                "apiEndpoint": "https://abc123.execute-api.sa-east-1.amazonaws.com",
                "executionArn": "arn:aws:execute-api:sa-east-1:123456789012:abc123",
            },
            "aws:acm/certificate:Certificate": {
                "domainValidationOptions": [{
                    "resourceRecordName": "_v.classly.test.",
                    "resourceRecordType": "CNAME",
                    "resourceRecordValue": "_v.acm-validations.aws.",
                }],
            },
            "aws:cloudfront/distribution:Distribution": {
                "domainName": "d111111abcdef8.cloudfront.net",
                "hostedZoneId": "Z2FDTNDATAQYW2",
            },
            "aws:sesv2/emailIdentity:EmailIdentity": {"dkimSigningAttributes": {"tokens": ["a1", "b2", "c3"]}},
            "aws:cognito/userPool:UserPool": {"endpoint": "cognito-idp.sa-east-1.amazonaws.com/sa-east-1_TEST"},
        }.get(args.typ, {})
        outputs.update(fake)
        outputs.setdefault("arn", f"arn:aws:mock:::{args.name}")
        outputs.setdefault("name", args.name)
        resources.append({"type": args.typ, "name": args.name, "provider": args.provider, "inputs": args.inputs})
        return [f"{args.name}-id", outputs]

    def call(self, args):
        return {"accountId": "123456789012", "id": f"{args.token}-id"}


config = {"aws:region": "sa-east-1", "classly:adminEmails": "coordenacao@classly.test"}
if STACK == "prod":
    config.update({
        "classly:domain": "classly.test",
        "classly:zoneId": "ZTEST",
        "classly:route53RoleArn": "arn:aws:iam::210987654321:role/route53-rr-role",
        "classly:route53ExternalId": "external-id",
    })

pulumi.runtime.set_mocks(Mocks(), project="Infra", stack=STACK, preview=False)
pulumi.runtime.set_all_config(config)
runpy.run_path(str(PROGRAM_DIR / "__main__.py"), run_name="__main__")

# Os registros são assíncronos: espera até nenhum recurso novo aparecer.
previous = -1
while previous != len(resources):
    previous = len(resources)
    pulumi.runtime.sync_await._sync_await(__import__("asyncio").sleep(1))

print("RESOURCES" + json.dumps(resources, default=str))
