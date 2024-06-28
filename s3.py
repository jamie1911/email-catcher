import json
import pulumi
import pulumi_aws as aws


from shared.aws.tagging import register_standard_tags
from config import stack, aws_account_id, product_name

register_standard_tags(environment=stack)

email_bucket = aws.s3.BucketV2(
    f"{product_name}_emails_bucket",
    bucket=f"{product_name}-emails".replace("_", "-"),
    force_destroy=True,
)
email_bucket_policy = aws.s3.BucketPolicy(
    f"{product_name}_email_bucket_policy",
    bucket=email_bucket.id,
    policy=pulumi.Output.all(email_bucket=email_bucket.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ses.amazonaws.com"},
                        "Action": "s3:PutObject",
                        "Resource": [
                            f"{args['email_bucket']}/*",
                        ],
                        "Condition": {"StringEquals": {"aws:Referer": aws_account_id}},
                    }
                ],
            }
        )
    ),
)
