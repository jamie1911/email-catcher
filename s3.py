import json
import pulumi
import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import stack, aws_account_id, product_name

register_standard_tags(environment=stack)

local_name = f"{product_name}_s3"

bucket_emails = aws.s3.BucketV2(
    f"{local_name}_emails",
    bucket=f"{product_name}-emails".replace("_", "-"),
    force_destroy=True,
)
pulumi.export("emails_bucket_name", bucket_emails.bucket)

aws.s3.BucketPolicy(
    f"{local_name}_emails_policy",
    bucket=bucket_emails.id,
    policy=pulumi.Output.all(bucket_emails=bucket_emails.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ses.amazonaws.com"},
                        "Action": "s3:PutObject",
                        "Resource": [
                            f"{args['bucket_emails']}/*",
                        ],
                        "Condition": {"StringEquals": {"aws:Referer": aws_account_id}},
                    }
                ],
            }
        )
    ),
)