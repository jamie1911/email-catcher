import sys
import pulumi_aws as aws

sys.path.insert(0, "../../../../")

from shared.aws.tagging import register_standard_tags
from config import (
    stack,
    product_name,
    email_domain,
    ses_domain_rule_set_name, email_route35_zone_id, aws_region
)
from aws_lambda import incoming_mail_check_function, incoming_mail_topic
from s3 import email_bucket

register_standard_tags(environment=stack)

receipt_rule = aws.ses.ReceiptRule(
    f"{product_name}_receipt_rule",
    rule_set_name=ses_domain_rule_set_name,
    lambda_actions=[
        aws.ses.ReceiptRuleLambdaActionArgs(
            position=1,
            function_arn=incoming_mail_check_function.arn,
            invocation_type="RequestResponse",
        )
    ],
    s3_actions=[
        aws.ses.ReceiptRuleS3ActionArgs(
            position=2,
            bucket_name=email_bucket.bucket,
            topic_arn=incoming_mail_topic.arn,
        )
    ],
    recipients=[email_domain],
    enabled=True,
    scan_enabled=True,
)

mx_record = aws.route53.Record(
    f"{product_name}_mx_record",
    zone_id=email_route35_zone_id,
    name=email_domain,
    type="MX",
    ttl=300,
    records=[f"10 inbound-smtp.{aws_region}.amazonaws.com"],
)