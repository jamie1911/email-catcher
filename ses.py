import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import (
    stack,
    product_name,
    ses_email_domain,
    ses_domain_rule_set_name,
    route35_email_zone_id,
    aws_region,
)
from aws_lambda import lambda_check_incoming_address, lambda_sns_check_incoming_address_topic
from s3 import bucket_emails

register_standard_tags(environment=stack)

local_name = f"{product_name}_ses"

aws.ses.ReceiptRule(
    f"{local_name}_receipt_rule",
    rule_set_name=ses_domain_rule_set_name,
    lambda_actions=[
        aws.ses.ReceiptRuleLambdaActionArgs(
            position=1,
            function_arn=lambda_check_incoming_address.arn,
            invocation_type="RequestResponse",
        )
    ],
    s3_actions=[
        aws.ses.ReceiptRuleS3ActionArgs(
            position=2,
            bucket_name=bucket_emails.bucket,
            topic_arn=lambda_sns_check_incoming_address_topic.arn,
            object_key_prefix="incoming_mail/",
        )
    ],
    recipients=[ses_email_domain],
    enabled=True,
    scan_enabled=True,
)

aws.route53.Record(
    f"{local_name}_mx_record",
    zone_id=route35_email_zone_id,
    name=ses_email_domain,
    type=aws.route53.RecordType.MX,
    ttl=300,
    records=[f"10 inbound-smtp.{aws_region}.amazonaws.com"],
)
