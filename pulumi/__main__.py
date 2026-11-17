"""Infraestrutura AWS do Classly.

dev: DynamoDB, Lambdas, API Gateway, Cognito, frontend no S3 e CloudFront com o
domínio padrão da CDN.
prod: o mesmo, publicado no domínio próprio com certificado ACM, e-mail SES do
domínio e registros Route 53 criados na zona compartilhada (via assume role).
"""

import json
import mimetypes
import re
import subprocess
from pathlib import Path

import pulumi
import pulumi_aws as aws

stack = pulumi.get_stack()
is_prod = stack == "prod"
config = pulumi.Config("classly")
region = pulumi.Config("aws").require("region")
account_id = aws.get_caller_identity().account_id

ROOT = Path(__file__).resolve().parent.parent
# Mesmo código das funções usado pelo SAM local (aws-sam/functions).
FUNCTIONS_DIR = ROOT / "aws-sam" / "functions"
WEB_DIR = ROOT / "web"
LOG_RETENTION_DAYS = 14

tags = {"Project": "Classly", "Environment": stack}

if is_prod:
    domain = config.require("domain")
    zone_id = config.require("zoneId")

    # A zona pertence a outra conta: os registros são criados assumindo o
    # papel route53-rr-role (permissão em iam-policy.json).
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

    def dns_record(resource_name, **kwargs):
        return aws.route53.Record(
            resource_name, zone_id=zone_id, opts=pulumi.ResourceOptions(provider=dns), **kwargs
        )


# --- DynamoDB ---
# Mesmo modelo de aws-sam/template.yaml e docs/api.md.
TABLE_KEYS = {
    "teachers": ("teacherId", None),
    "subjects": ("subjectId", None),
    "classes": ("classId", None),
    "qualifications": ("teacherId", "subjectId"),
    "availability": ("teacherId", "availabilityId"),
    "schedules": ("scheduleId", None),
    "users": ("userId", None),
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

# --- API Gateway (HTTP API) ---
api = aws.apigatewayv2.Api("classly-api", protocol_type="HTTP", tags=tags)

aws.apigatewayv2.Stage(
    "classly-stage", api_id=api.id, name="$default", auto_deploy=True, tags=tags
)

# --- Frontend: bucket privado lido apenas pelo CloudFront (OAC) ---
web_bucket = aws.s3.Bucket("classly-web", force_destroy=not is_prod, tags=tags)
aws.s3.BucketPublicAccessBlock(
    "classly-web-private",
    bucket=web_bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True,
)
web_oac = aws.cloudfront.OriginAccessControl(
    "classly-web-oac",
    origin_access_control_origin_type="s3",
    signing_behavior="always",
    signing_protocol="sigv4",
)

# --- CloudFront: site em /, API em /api/* (+ ACM em prod) ---
aliases = []
viewer_cert = aws.cloudfront.DistributionViewerCertificateArgs(
    cloudfront_default_certificate=True
)

if is_prod:
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
    validation_record = dns_record(
        "classly-cert-validation",
        name=validation.resource_record_name,
        type=validation.resource_record_type,
        records=[validation.resource_record_value],
        ttl=60,
        allow_overwrite=True,
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
# cabeçalhos (inclusive Authorization), query string e corpo ao API Gateway.
caching_disabled = aws.cloudfront.get_cache_policy(name="Managed-CachingDisabled")
caching_optimized = aws.cloudfront.get_cache_policy(name="Managed-CachingOptimized")
all_viewer_except_host = aws.cloudfront.get_origin_request_policy(
    name="Managed-AllViewerExceptHostHeader"
)

# O frontend chama /api/teachers; a API conhece /teachers.
strip_api_prefix = aws.cloudfront.Function(
    "classly-strip-api",
    runtime="cloudfront-js-2.0",
    comment="Remove o prefixo /api antes de encaminhar ao API Gateway",
    publish=True,
    code="""function handler(event) {
  var request = event.request;
  request.uri = request.uri.replace(/^\\/api(?=\\/|$)/, '') || '/';
  return request;
}
""",
)

api_hostname = api.api_endpoint.apply(lambda e: e.replace("https://", "").split("/")[0])

distribution = aws.cloudfront.Distribution(
    "classly-cdn",
    enabled=True,
    is_ipv6_enabled=True,
    http_version="http2and3",
    comment=f"Classly ({stack})",
    aliases=aliases,
    default_root_object="index.html",
    origins=[
        aws.cloudfront.DistributionOriginArgs(
            domain_name=web_bucket.bucket_regional_domain_name,
            origin_id="web",
            origin_access_control_id=web_oac.id,
        ),
        aws.cloudfront.DistributionOriginArgs(
            domain_name=api_hostname,
            origin_id="api",
            custom_origin_config=aws.cloudfront.DistributionOriginCustomOriginConfigArgs(
                http_port=80,
                https_port=443,
                origin_protocol_policy="https-only",
                origin_ssl_protocols=["TLSv1.2"],
            ),
        ),
    ],
    default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
        target_origin_id="web",
        viewer_protocol_policy="redirect-to-https",
        allowed_methods=["GET", "HEAD"],
        cached_methods=["GET", "HEAD"],
        cache_policy_id=caching_optimized.id,
        compress=True,
    ),
    ordered_cache_behaviors=[
        aws.cloudfront.DistributionOrderedCacheBehaviorArgs(
            path_pattern="/api/*",
            target_origin_id="api",
            viewer_protocol_policy="redirect-to-https",
            allowed_methods=["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
            cached_methods=["GET", "HEAD"],
            cache_policy_id=caching_disabled.id,
            origin_request_policy_id=all_viewer_except_host.id,
            compress=True,
            function_associations=[
                aws.cloudfront.DistributionOrderedCacheBehaviorFunctionAssociationArgs(
                    event_type="viewer-request", function_arn=strip_api_prefix.arn
                )
            ],
        )
    ],
    viewer_certificate=viewer_cert,
    restrictions=aws.cloudfront.DistributionRestrictionsArgs(
        geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
            restriction_type="none"
        )
    ),
    tags=tags,
)

app_url = (
    pulumi.Output.from_input(f"https://{domain}")
    if is_prod
    else distribution.domain_name.apply(lambda d: f"https://{d}")
)

aws.s3.BucketPolicy(
    "classly-web-policy",
    bucket=web_bucket.id,
    policy=pulumi.Output.all(web_bucket.arn, distribution.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudfront.amazonaws.com"},
                        "Action": "s3:GetObject",
                        "Resource": f"{args[0]}/*",
                        "Condition": {"StringEquals": {"AWS:SourceArn": args[1]}},
                    }
                ],
            }
        )
    ),
)

# --- Cognito: base de usuários, verificação por e-mail e login gerenciado ---
user_pool = aws.cognito.UserPool(
    "classly-users",
    username_attributes=["email"],
    auto_verified_attributes=["email"],
    username_configuration=aws.cognito.UserPoolUsernameConfigurationArgs(case_sensitive=False),
    schemas=[
        aws.cognito.UserPoolSchemaArgs(
            name="name",
            attribute_data_type="String",
            required=True,
            mutable=True,
            string_attribute_constraints=aws.cognito.UserPoolSchemaStringAttributeConstraintsArgs(
                min_length="1", max_length="256"
            ),
        )
    ],
    password_policy=aws.cognito.UserPoolPasswordPolicyArgs(
        minimum_length=8,
        require_lowercase=True,
        require_numbers=True,
        require_uppercase=True,
        require_symbols=False,
        temporary_password_validity_days=7,
    ),
    account_recovery_setting=aws.cognito.UserPoolAccountRecoverySettingArgs(
        recovery_mechanisms=[
            aws.cognito.UserPoolAccountRecoverySettingRecoveryMechanismArgs(
                name="verified_email", priority=1
            )
        ]
    ),
    verification_message_template=aws.cognito.UserPoolVerificationMessageTemplateArgs(
        default_email_option="CONFIRM_WITH_CODE",
        email_subject="Classly: código de verificação",
        email_message="Olá! Seu código de verificação do Classly é {####}.",
    ),
    email_configuration=aws.cognito.UserPoolEmailConfigurationArgs(
        email_sending_account="COGNITO_DEFAULT"
    ),
    deletion_protection="ACTIVE" if is_prod else "INACTIVE",
    tags=tags,
)

auth_domain = aws.cognito.UserPoolDomain(
    "classly-auth",
    domain=f"classly-{stack}-{account_id}",
    user_pool_id=user_pool.id,
    managed_login_version=2,
)

identity_providers = ["COGNITO"]
idp_resources = []
google_client_id = config.get("googleClientId")
if google_client_id:
    idp_resources.append(
        aws.cognito.IdentityProvider(
            "classly-google",
            user_pool_id=user_pool.id,
            provider_name="Google",
            provider_type="Google",
            provider_details={
                "client_id": google_client_id,
                "client_secret": config.require_secret("googleClientSecret"),
                "authorize_scopes": "openid email profile",
            },
            attribute_mapping={
                "email": "email",
                "email_verified": "email_verified",
                "name": "name",
                "username": "sub",
            },
        )
    )
    identity_providers.append("Google")

web_client = aws.cognito.UserPoolClient(
    "classly-web",
    user_pool_id=user_pool.id,
    generate_secret=False,
    allowed_oauth_flows_user_pool_client=True,
    allowed_oauth_flows=["code"],
    allowed_oauth_scopes=["openid", "email", "profile"],
    callback_urls=[app_url.apply(lambda u: f"{u}/")],
    logout_urls=[app_url],
    supported_identity_providers=identity_providers,
    explicit_auth_flows=["ALLOW_REFRESH_TOKEN_AUTH"],
    prevent_user_existence_errors="ENABLED",
    enable_token_revocation=True,
    id_token_validity=60,
    access_token_validity=60,
    refresh_token_validity=30,
    token_validity_units=aws.cognito.UserPoolClientTokenValidityUnitsArgs(
        id_token="minutes", access_token="minutes", refresh_token="days"
    ),
    opts=pulumi.ResourceOptions(depends_on=idp_resources),
)

aws.cognito.ManagedLoginBranding(
    "classly-login-branding",
    user_pool_id=user_pool.id,
    client_id=web_client.id,
    use_cognito_provided_values=True,
)

# A API só aceita ID tokens emitidos para o cliente web do Classly.
jwt_authorizer = aws.apigatewayv2.Authorizer(
    "classly-jwt",
    api_id=api.id,
    name="cognito",
    authorizer_type="JWT",
    identity_sources=["$request.header.Authorization"],
    jwt_configuration=aws.apigatewayv2.AuthorizerJwtConfigurationArgs(
        audiences=[web_client.id],
        issuer=user_pool.endpoint.apply(lambda e: f"https://{e}"),
    ),
)

# --- SES: e-mail de publicação de grades ---
# prod: domínio verificado por DKIM. dev: endereço em classly:senderEmail
# (a AWS envia um link de confirmação para ele). Sem remetente, a publicação
# funciona e informa que os e-mails não foram enviados.
sender_email = None
if is_prod:
    email_identity = aws.sesv2.EmailIdentity("classly-email", email_identity=domain, tags=tags)
    for i in range(3):
        token = email_identity.dkim_signing_attributes.tokens[i]
        dns_record(
            f"classly-dkim-{i}",
            name=token.apply(lambda t: f"{t}._domainkey.{domain}"),
            type="CNAME",
            records=[token.apply(lambda t: f"{t}.dkim.amazonses.com")],
            ttl=300,
        )
    sender_email = f"Classly <noreply@{domain}>"
elif config.get("senderEmail"):
    aws.sesv2.EmailIdentity("classly-email", email_identity=config.get("senderEmail"), tags=tags)
    sender_email = config.get("senderEmail")

# --- Lambdas ---
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

function_env = aws.lambda_.FunctionEnvironmentArgs(
    variables={
        **{f"{name.upper()}_TABLE": table.name for name, table in tables.items()},
        "ADMIN_EMAILS": config.require("adminEmails"),
        "SENDER_EMAIL": sender_email or "",
        "APP_URL": app_url,
    }
)


def api_function(name, handler, routes, table_names=(), public=False, send_email=False):
    """Cria a função com papel próprio (menor privilégio) e liga suas rotas à API.

    Toda rota protegida consulta o perfil do usuário (tabela users) e o vínculo
    com o professor (tabela teachers).
    """
    if not public:
        table_names = sorted(set(table_names) | {"users", "teachers"})
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
    if send_email:
        aws.iam.RolePolicy(
            f"{name}-ses",
            role=role.id,
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [{"Effect": "Allow", "Action": "ses:SendEmail", "Resource": "*"}],
                }
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
        environment=function_env,
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
            authorization_type="NONE" if public else "JWT",
            authorizer_id=None if public else jwt_authorizer.id,
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
        ["GET /qualifications", "ANY /teachers/{teacherId}/subjects/{subjectId}"],
        ["qualifications", "subjects"],
    ),
    "availability": api_function(
        "classly-availability",
        "availability.handler.handler",
        ["ANY /teachers/{teacherId}/availability"],
        ["availability"],
    ),
    "schedules": api_function(
        "classly-schedules",
        "schedules.handler.handler",
        [
            "GET /schedules",
            "POST /schedules",
            "POST /schedules/validate",
            "ANY /schedules/{scheduleId}",
            "POST /schedules/{scheduleId}/publish",
        ],
        list(TABLE_KEYS),
        send_email=True,
    ),
    "users": api_function(
        "classly-users",
        "users.handler.handler",
        ["GET /me", "GET /users", "PUT /users/{userId}/role"],
    ),
    "health": api_function("classly-health", "health.handler.handler", ["GET /health"], public=True),
}

# --- Publicação do frontend ---
# O build roda a cada `pulumi up`/`preview`; config.json é gerado aqui com os
# endereços reais do Cognito e substitui o arquivo de desenvolvimento local.
subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=WEB_DIR, check=True)
subprocess.run(["npm", "run", "build"], cwd=WEB_DIR, check=True)

dist_dir = WEB_DIR / "dist"
for file_path in sorted(dist_dir.rglob("*")):
    relative = file_path.relative_to(dist_dir).as_posix()
    if not file_path.is_file() or relative == "config.json":
        continue
    # Arquivos em assets/ têm hash no nome e podem ficar em cache por um ano.
    immutable = relative.startswith("assets/")
    aws.s3.BucketObject(
        f"web-{re.sub(r'[^A-Za-z0-9]+', '-', relative)}",
        bucket=web_bucket.id,
        key=relative,
        source=pulumi.FileAsset(str(file_path)),
        content_type=mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
        cache_control="public, max-age=31536000, immutable" if immutable else "no-cache",
    )

aws.s3.BucketObject(
    "web-config-json",
    bucket=web_bucket.id,
    key="config.json",
    content=pulumi.Output.json_dumps(
        {
            "apiBase": "/api",
            "auth": {
                "domain": auth_domain.domain.apply(
                    lambda d: f"https://{d}.auth.{region}.amazoncognito.com"
                ),
                "clientId": web_client.id,
                "redirectUri": app_url.apply(lambda u: f"{u}/"),
                "logoutUri": app_url,
                "identityProviders": identity_providers,
            },
        }
    ),
    content_type="application/json",
    cache_control="no-cache",
)

if is_prod:
    # Registros básicos do domínio: apex apontando para a CDN (IPv4 e IPv6).
    for rtype in ["A", "AAAA"]:
        dns_record(
            f"classly-alias-{rtype.lower()}",
            name=domain,
            type=rtype,
            aliases=[
                aws.route53.RecordAliasArgs(
                    name=distribution.domain_name,
                    zone_id=distribution.hosted_zone_id,
                    evaluate_target_health=False,
                )
            ],
        )

pulumi.export("environment", stack)
pulumi.export("url", app_url)
pulumi.export("api_url", api.api_endpoint)
pulumi.export("cdn_domain", distribution.domain_name)
pulumi.export("user_pool_id", user_pool.id)
pulumi.export("web_client_id", web_client.id)
pulumi.export(
    "login_url", auth_domain.domain.apply(lambda d: f"https://{d}.auth.{region}.amazoncognito.com")
)
pulumi.export("sender_email", sender_email or "não configurado")
pulumi.export("tables", {name: table.name for name, table in tables.items()})
pulumi.export("functions", {name: fn.name for name, fn in functions.items()})
