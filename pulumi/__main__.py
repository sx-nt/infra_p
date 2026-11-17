"""Infraestrutura AWS do Classly.

dev: DynamoDB, Lambdas, API Gateway e CloudFront com o domínio padrão da CDN.
prod: o mesmo, publicado no domínio próprio com certificado ACM e registros
Route 53 criados na zona compartilhada (acesso via assume role).
"""

import json
import re
from pathlib import Path

import pulumi
import pulumi_aws as aws

stack = pulumi.get_stack()
is_prod = stack == "prod"
config = pulumi.Config("classly")

# Mesmo código das funções usado pelo SAM local (aws-sam/functions).
FUNCTIONS_DIR = Path(__file__).parent.parent / "aws-sam" / "functions"
LOG_RETENTION_DAYS = 14

tags = {"Project": "Classly", "Environment": stack}

# --- DynamoDB ---
# Mesmo modelo de aws-sam/template.yaml e docs/api.md.
TABLE_KEYS = {
    "teachers": ("teacherId", None),
    "subjects": ("subjectId", None),
    "classes": ("classId", None),
    "qualifications": ("teacherId", "subjectId"),
    "availability": ("teacherId", "availabilityId"),
    "schedules": ("scheduleId", None),
}

tables = {}
for name, (hash_key, range_key) in TABLE_KEYS.items():
    keys = [hash_key] + ([range_key] if range_key else [])
    tables[name] = aws.dynamodb.Table(
        f"classly-{name}",
        attributes=[aws.dynamodb.TableAttributeArgs(name=k, type="S") for k in keys],
        hash_key=hash_key,
        range_key=range_key,
        billing_mode="PAY_PER_REQUEST",
        point_in_time_recovery=aws.dynamodb.TablePointInTimeRecoveryArgs(enabled=is_prod),
        tags=tags,
    )

table_env = aws.lambda_.FunctionEnvironmentArgs(
    variables={f"{name.upper()}_TABLE": table.name for name, table in tables.items()}
)

# --- API Gateway (HTTP API) ---
api = aws.apigatewayv2.Api(
    "classly-api",
    protocol_type="HTTP",
    cors_configuration=aws.apigatewayv2.ApiCorsConfigurationArgs(
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    ),
    tags=tags,
)

aws.apigatewayv2.Stage(
    "classly-stage", api_id=api.id, name="$default", auto_deploy=True, tags=tags
)

LAMBDA_ASSUME_ROLE = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)

DYNAMODB_ACTIONS = [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:DeleteItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:BatchWriteItem",
]


# --- Lambdas ---
def api_function(name, handler, routes, table_names=()):
    """Cria a função com papel próprio (menor privilégio) e liga suas rotas à API."""
    role = aws.iam.Role(f"{name}-role", assume_role_policy=LAMBDA_ASSUME_ROLE, tags=tags)
    aws.iam.RolePolicyAttachment(
        f"{name}-logs",
        role=role.name,
        policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )
    if table_names:
        aws.iam.RolePolicy(
            f"{name}-dynamodb",
            role=role.id,
            policy=pulumi.Output.all(*[tables[t].arn for t in table_names]).apply(
                lambda arns: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {"Effect": "Allow", "Action": DYNAMODB_ACTIONS, "Resource": arns}
                        ],
                    }
                )
            ),
        )

    log_group = aws.cloudwatch.LogGroup(
        f"{name}-log-group", retention_in_days=LOG_RETENTION_DAYS, tags=tags
    )
    fn = aws.lambda_.Function(
        name,
        role=role.arn,
        runtime=aws.lambda_.Runtime.PYTHON3D12,
        handler=handler,
        code=pulumi.FileArchive(str(FUNCTIONS_DIR)),
        timeout=20,
        memory_size=256,
        environment=table_env,
        logging_config=aws.lambda_.FunctionLoggingConfigArgs(
            log_format="Text", log_group=log_group.name
        ),
        tags=tags,
    )

    integration = aws.apigatewayv2.Integration(
        f"{name}-integration",
        api_id=api.id,
        integration_type="AWS_PROXY",
        integration_method="POST",
        integration_uri=fn.invoke_arn,
        payload_format_version="2.0",
    )
    for route_key in routes:
        slug = re.sub(r"[^a-z0-9]+", "-", route_key.lower()).strip("-")
        aws.apigatewayv2.Route(
            f"{name}-{slug}",
            api_id=api.id,
            route_key=route_key,
            target=integration.id.apply(lambda i: f"integrations/{i}"),
        )
    aws.lambda_.Permission(
        f"{name}-apigw-permission",
        function=fn.name,
        action="lambda:InvokeFunction",
        principal="apigateway.amazonaws.com",
        source_arn=api.execution_arn.apply(lambda a: f"{a}/*/*"),
    )
    return fn


# Rotas e permissões espelham os eventos e políticas de aws-sam/template.yaml.
functions = {
    "teachers": api_function(
        "classly-teachers",
        "teachers.handler.handler",
        ["GET /teachers", "POST /teachers", "ANY /teachers/{teacherId}"],
        ["teachers"],
    ),
    "subjects": api_function(
        "classly-subjects",
        "subjects.handler.handler",
        ["GET /subjects", "POST /subjects", "ANY /subjects/{subjectId}"],
        # DELETE consulta turmas associadas antes de remover a disciplina.
        ["subjects", "classes"],
    ),
    "classes": api_function(
        "classly-classes",
        "classes.handler.handler",
        ["GET /classes", "POST /classes", "ANY /classes/{classId}"],
        ["classes", "subjects"],
    ),
    "qualifications": api_function(
        "classly-qualifications",
        "qualifications.handler.handler",
        ["ANY /teachers/{teacherId}/subjects/{subjectId}"],
        ["qualifications", "teachers", "subjects"],
    ),
    "availability": api_function(
        "classly-availability",
        "availability.handler.handler",
        ["ANY /teachers/{teacherId}/availability"],
        ["availability", "teachers"],
    ),
    "schedules": api_function(
        "classly-schedules",
        "schedules.handler.handler",
        ["POST /schedules", "POST /schedules/validate", "GET /schedules/{scheduleId}"],
        list(TABLE_KEYS),
    ),
    "health": api_function("classly-health", "health.handler.handler", ["GET /health"]),
}

# --- CloudFront (+ ACM e Route 53 em prod) ---
aliases = []
viewer_cert = aws.cloudfront.DistributionViewerCertificateArgs(
    cloudfront_default_certificate=True
)

if is_prod:
    domain = config.require("domain")
    zone_id = config.require("zoneId")

    # A zona pertence a outra conta: os registros são criados assumindo o
    # papel route53-rr-role (ver pulumi/assume-policy.json).
    dns = aws.Provider(
        "route53-shared-zone",
        region="us-east-1",
        assume_roles=[
            aws.ProviderAssumeRoleArgs(
                role_arn=config.require("route53RoleArn"),
                external_id=config.require("route53ExternalId"),
                session_name=f"classly-{stack}",
            )
        ],
    )
    # O CloudFront só aceita certificados emitidos em us-east-1.
    us_east_1 = aws.Provider("us-east-1", region="us-east-1")

    cert = aws.acm.Certificate(
        "classly-cert",
        domain_name=domain,
        validation_method="DNS",
        tags=tags,
        opts=pulumi.ResourceOptions(provider=us_east_1),
    )

    validation = cert.domain_validation_options[0]
    validation_record = aws.route53.Record(
        "classly-cert-validation",
        zone_id=zone_id,
        name=validation.resource_record_name,
        type=validation.resource_record_type,
        records=[validation.resource_record_value],
        ttl=60,
        allow_overwrite=True,
        opts=pulumi.ResourceOptions(provider=dns),
    )

    cert_validation = aws.acm.CertificateValidation(
        "classly-cert-validation",
        certificate_arn=cert.arn,
        validation_record_fqdns=[validation_record.fqdn],
        opts=pulumi.ResourceOptions(provider=us_east_1),
    )

    aliases = [domain]
    viewer_cert = aws.cloudfront.DistributionViewerCertificateArgs(
        acm_certificate_arn=cert_validation.certificate_arn,
        ssl_support_method="sni-only",
        minimum_protocol_version="TLSv1.2_2021",
    )

# A API responde dados dinâmicos por usuário: sem cache, repassando
# cabeçalhos, query string e cookies (exceto Host) para o API Gateway.
caching_disabled = aws.cloudfront.get_cache_policy(name="Managed-CachingDisabled")
all_viewer_except_host = aws.cloudfront.get_origin_request_policy(
    name="Managed-AllViewerExceptHostHeader"
)

api_hostname = api.api_endpoint.apply(lambda e: e.replace("https://", "").split("/")[0])

distribution = aws.cloudfront.Distribution(
    "classly-cdn",
    enabled=True,
    is_ipv6_enabled=True,
    http_version="http2and3",
    comment=f"Classly ({stack})",
    aliases=aliases,
    origins=[
        aws.cloudfront.DistributionOriginArgs(
            domain_name=api_hostname,
            origin_id="api",
            custom_origin_config=aws.cloudfront.DistributionOriginCustomOriginConfigArgs(
                http_port=80,
                https_port=443,
                origin_protocol_policy="https-only",
                origin_ssl_protocols=["TLSv1.2"],
            ),
        )
    ],
    default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
        target_origin_id="api",
        viewer_protocol_policy="redirect-to-https",
        allowed_methods=["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
        cached_methods=["GET", "HEAD"],
        cache_policy_id=caching_disabled.id,
        origin_request_policy_id=all_viewer_except_host.id,
        compress=True,
    ),
    viewer_certificate=viewer_cert,
    restrictions=aws.cloudfront.DistributionRestrictionsArgs(
        geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
            restriction_type="none"
        )
    ),
    tags=tags,
)

if is_prod:
    # Registros básicos do domínio: apex apontando para a CDN (IPv4 e IPv6).
    for rtype in ["A", "AAAA"]:
        aws.route53.Record(
            f"classly-alias-{rtype.lower()}",
            zone_id=zone_id,
            name=domain,
            type=rtype,
            aliases=[
                aws.route53.RecordAliasArgs(
                    name=distribution.domain_name,
                    zone_id=distribution.hosted_zone_id,
                    evaluate_target_health=False,
                )
            ],
            opts=pulumi.ResourceOptions(provider=dns),
        )

pulumi.export("environment", stack)
pulumi.export("tables", {name: table.name for name, table in tables.items()})
pulumi.export("functions", {name: fn.name for name, fn in functions.items()})
pulumi.export("api_url", api.api_endpoint)
pulumi.export("cdn_domain", distribution.domain_name)
pulumi.export(
    "url",
    f"https://{domain}" if is_prod else distribution.domain_name.apply(lambda d: f"https://{d}"),
)
