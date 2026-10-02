"""Infraestrutura AWS do Classly."""

import pulumi
from pulumi_aws import s3

stack = pulumi.get_stack()

# O estado de dev e prod é separado pelo Pulumi; o nome lógico pode ser igual.
bucket = s3.Bucket(
    "classly-assets",
    tags={
        "Project": "Classly",
        "Environment": stack,
    },
)

pulumi.export("environment", stack)
pulumi.export("bucket_name", bucket.id)
