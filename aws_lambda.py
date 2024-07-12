import json
import pulumi
import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import (
    stack,
    aws_account_id,
    product_name,
    ses_email_domain,
    log_level,
    xray_enabled,
)
from dynamodb import table_addresses, table_emails
from s3 import bucket_emails

register_standard_tags(environment=stack)

local_name = f"{product_name}_lambda"
LAMBDA_TIMEOUT = 120
LAMBDA_PYTHON_VERSION = "python3.12"

lambda_code_layer = aws.lambda_.LayerVersion(
    f"{local_name}_code_layer",
    compatible_runtimes=[LAMBDA_PYTHON_VERSION],
    code=pulumi.FileArchive("./code_layer"),
    skip_destroy=False,
    layer_name=f"{product_name}_lambda_code_layer",
)
local_archive = pulumi.FileArchive("./lambda")

lambda_cloudwatch_log_group = aws.cloudwatch.LogGroup(
    f"{local_name}_cloudwatch_log_group",
    retention_in_days=7,
    skip_destroy=False
)

lambda_incoming_email_check_role = aws.iam.Role(
    f"{local_name}_incoming_email_check_role",
    assume_role_policy=json.dumps(
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
    ),
    managed_policy_arns=[aws.iam.ManagedPolicy.AWSX_RAY_DAEMON_WRITE_ACCESS],
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="cloudwatch_logs_policy",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": "arn:aws:logs:*:*:*",
                        }
                    ],
                }
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="access_policy",
            policy=pulumi.Output.all(addresses_table_arn=table_addresses.arn).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "dynamodb:GetItem",
                                "Resource": args["addresses_table_arn"],
                            },
                        ],
                    }
                )
            ),
        ),
    ],
)

lambda_incoming_email_check = aws.lambda_.Function(
    f"{local_name}_incoming_email_check",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Invoked by SES to check if email address exists.",
    handler="incoming_email_check_function.lambda_handler",
    role=lambda_incoming_email_check_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
            "EMAILS_TABLE_NAME": table_emails.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)

aws.lambda_.Permission(
    f"{local_name}_incoming_email_check_permission",
    action="lambda:InvokeFunction",
    function=lambda_incoming_email_check.arn,
    principal="ses.amazonaws.com",
    source_account=aws_account_id,
)

lambda_store_email_role = aws.iam.Role(
    f"{local_name}_store_email_role",
    assume_role_policy=json.dumps(
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
    ),
    managed_policy_arns=[aws.iam.ManagedPolicy.AWSX_RAY_DAEMON_WRITE_ACCESS],
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="cloudwatch_logs_policy",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": "arn:aws:logs:*:*:*",
                        }
                    ],
                }
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="access_policy",
            policy=pulumi.Output.all(
                emails_table_arn=table_emails.arn,
                address_table_arn=table_addresses.arn,
                email_bucket_arn=bucket_emails.arn,
            ).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["dynamodb:PutItem", "dynamodb:UpdateItem"],
                                "Resource": args["emails_table_arn"],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "dynamodb:GetItem",
                                "Resource": args["address_table_arn"],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "s3:GetObject",
                                "Resource": f"{args['email_bucket_arn']}/*",
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["bedrock:InvokeModel"],
                                "Resource": ["*"],
                            },
                        ],
                    }
                )
            ),
        ),
    ],
)

lambda_store_email = aws.lambda_.Function(
    f"{local_name}_store_email",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Incoming email topic subscriber to store emails and s3 object locations in db",
    handler="store_email_function.lambda_handler",
    role=lambda_store_email_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
            "EMAILS_TABLE_NAME": table_emails.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)

lambda_sns_incoming_email_topic = aws.sns.Topic(
    f"{local_name}_sns_incoming_email_topic",
    display_name="Store Successful Incoming Email Topic",
    tracing_config="Active" if xray_enabled.lower() == "true" else None,
)
lambda_sns_incoming_mail_topic_subscription = aws.sns.TopicSubscription(
    f"{local_name}_sns_incoming_mail_topic_subscription",
    topic=lambda_sns_incoming_email_topic.arn,
    protocol="lambda",
    endpoint=lambda_store_email.arn,
)

lambda_sns_incoming_mail_topic_policy = aws.sns.TopicPolicy(
    f"{local_name}_sns_incoming_mail_topic_policy",
    arn=lambda_sns_incoming_email_topic.arn,
    policy=pulumi.Output.all(
        incoming_mail_topic_arn=lambda_sns_incoming_email_topic.arn
    ).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "sns:Publish",
                        "Resource": args["incoming_mail_topic_arn"],
                        "Principal": {"Service": "ses.amazonaws.com"},
                        "Condition": {
                            "ArnLike": {
                                "AWS:SourceArn": f"arn:aws:*:*:{aws_account_id}:*"
                            }
                        },
                    }
                ],
            }
        )
    ),
)

aws.lambda_.Permission(
    f"{local_name}_sns_store_email_permission",
    action="lambda:InvokeFunction",
    function=lambda_store_email.arn,
    principal="sns.amazonaws.com",
    source_arn=lambda_sns_incoming_email_topic.arn,
)


lambda_addresses_emails_role = aws.iam.Role(
    f"{local_name}_addresses_emails_role",
    assume_role_policy=json.dumps(
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
    ),
    managed_policy_arns=[aws.iam.ManagedPolicy.AWSX_RAY_DAEMON_WRITE_ACCESS],
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="cloudwatch_logs_policy",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": "arn:aws:logs:*:*:*",
                        }
                    ],
                }
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="access_policy",
            policy=pulumi.Output.all(
                emails_table_arn=table_emails.arn,
                addresses_table_arn=table_addresses.arn,
            ).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "dynamodb:GetItem",
                                    "dynamodb:Query",
                                    "dynamodb:PutItem",
                                ],
                                "Resource": [
                                    f"{args['emails_table_arn']}*",
                                    f"{args['addresses_table_arn']}*",
                                ],
                            },
                        ],
                    }
                )
            ),
        ),
    ],
)

lambda_get_emails = aws.lambda_.Function(
    f"{local_name}_get_emails",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Gets the list of emails for a specific address",
    handler="get_emails_list_function.lambda_handler",
    role=lambda_addresses_emails_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "EMAILS_TABLE_NAME": table_emails.name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)

lambda_get_addresses = aws.lambda_.Function(
    f"{local_name}_get_addresses",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Gets the list of email addresses for a specific user",
    handler="get_addresses_function.lambda_handler",
    role=lambda_addresses_emails_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)

lambda_post_addresses = aws.lambda_.Function(
    f"{local_name}_post_addresses",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Create email address for a specific user",
    handler="post_addresses_function.lambda_handler",
    role=lambda_addresses_emails_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
            "EMAIL_DOMAIN": ses_email_domain,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)

lambda_delete_address_email_role = aws.iam.Role(
    f"{local_name}_delete_address_email_role",
    assume_role_policy=json.dumps(
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
    ),
    managed_policy_arns=[aws.iam.ManagedPolicy.AWSX_RAY_DAEMON_WRITE_ACCESS],
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="cloudwatch_logs_policy",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": "arn:aws:logs:*:*:*",
                        }
                    ],
                }
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="access_policy",
            policy=pulumi.Output.all(
                emails_table_arn=table_emails.arn,
                addresses_table_arn=table_addresses.arn,
                incoming_mail_bucket_arn=bucket_emails.arn,
            ).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "dynamodb:DeleteItem",
                                    "dynamodb:GetItem",
                                    "dynamodb:Scan",
                                    "dynamodb:Query",
                                ],
                                "Resource": [
                                    args["emails_table_arn"],
                                    args["addresses_table_arn"],
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "s3:DeleteObject",
                                "Resource": f"{args['incoming_mail_bucket_arn']}/*",
                            },
                        ],
                    }
                )
            ),
        ),
    ],
)

lambda_delete_address = aws.lambda_.Function(
    f"{local_name}_delete_address",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Delete email address for a specific user",
    handler="delete_address_function.lambda_handler",
    role=lambda_delete_address_email_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "EMAILS_TABLE_NAME": table_emails.name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)

lambda_delete_email_item = aws.lambda_.Function(
    f"{local_name}_delete_email_item",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Delete email item from an address for a specific user",
    handler="delete_email_item_function.lambda_handler",
    role=lambda_delete_address_email_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "EMAILS_TABLE_NAME": table_emails.name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)

lambda_get_email_role = aws.iam.Role(
    f"{local_name}_get_email_role",
    assume_role_policy=json.dumps(
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
    ),
    managed_policy_arns=[aws.iam.ManagedPolicy.AWSX_RAY_DAEMON_WRITE_ACCESS],
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="cloudwatch_logs_policy",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": "arn:aws:logs:*:*:*",
                        }
                    ],
                }
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="access_policy",
            policy=pulumi.Output.all(
                addresses_table_arn=table_addresses.arn,
                emails_table_arn=table_emails.arn,
                email_bucket_arn=bucket_emails.arn,
            ).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["dynamodb:GetItem", "dynamodb:UpdateItem"],
                                "Resource": [
                                    args["emails_table_arn"],
                                    args["addresses_table_arn"],
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "s3:GetObject",
                                "Resource": f"{args['email_bucket_arn']}/*",
                            },
                        ],
                    }
                )
            ),
        ),
    ],
)

lambda_get_email = aws.lambda_.Function(
    f"{local_name}_get_email",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Get contents of a specific email for a user",
    handler="get_email_function.lambda_handler",
    role=lambda_get_email_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "EMAILS_TABLE_NAME": table_emails.name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT,
    layers=[lambda_code_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
    logging_config=aws.lambda_.FunctionLoggingConfigArgs(
        log_format="JSON",
        application_log_level=log_level,
        system_log_level=log_level,
        log_group=lambda_cloudwatch_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_cloudwatch_log_group]),
)
