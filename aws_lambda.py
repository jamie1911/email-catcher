import json
import sys
import pulumi
import pulumi_aws as aws

sys.path.insert(0, "../../../../")

from shared.aws.tagging import register_standard_tags
from config import (
    stack,
    aws_account_id,
    product_name,
    email_domain,
    log_level,
    xray_enabled,
)
from dynamodb import addresses_table, emails_table
from s3 import email_bucket

register_standard_tags(environment=stack)

lambda_layer = aws.lambda_.LayerVersion(
    f"{product_name}_lambda_code_layer",
    compatible_runtimes=["python3.10"],
    code=pulumi.FileArchive("./code_layer"),
    skip_destroy=False,
    layer_name=f"{product_name}_lambda_code_layer",
)
local_archive = pulumi.FileArchive("./lambda")

incoming_mail_check_function_role = aws.iam.Role(
    f"{product_name}_incoming_mail_check_function_role",
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
            name="dynamodb_policy",
            policy=pulumi.Output.all(addresses_table_arn=addresses_table.arn).apply(
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

incoming_mail_check_function = aws.lambda_.Function(
    f"{product_name}_incoming_mail_check_function",
    runtime="python3.10",
    description="Invoked by SES to check if mail address exists.",
    handler="incoming_mail_check_function.lambda_handler",
    role=incoming_mail_check_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "addresses_table_name": addresses_table.name,
            "emails_table_name": emails_table.name,
        }
    ),
    timeout=30,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)

aws.lambda_.Permission(
    f"{product_name}_incoming_mail_check_function_permission",
    action="lambda:InvokeFunction",
    function=incoming_mail_check_function.arn,
    principal="ses.amazonaws.com",
    source_account=aws_account_id,
)

store_email_function_role = aws.iam.Role(
    f"{product_name}_store_email_function_role",
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
                emails_table_arn=emails_table.arn,
                address_table_arn=addresses_table.arn,
                email_bucket=email_bucket.arn
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
                                "Resource": f"{args['email_bucket']}/*",
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

store_email_function = aws.lambda_.Function(
    f"{product_name}_store_email_function",
    runtime="python3.10",
    description="Incoming mail topic subscriber to store emails in db.",
    handler="store_email_function.lambda_handler",
    role=store_email_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "addresses_table_name": addresses_table.name,
            "emails_table_name": emails_table.name,
        }
    ),
    timeout=120,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)

incoming_mail_topic = aws.sns.Topic(
    f"{product_name}_incoming_mail_topic",
    display_name="Disposable incoming mail topic",
    tracing_config="Active" if xray_enabled.lower() == "true" else None,
)
incoming_mail_topic_subscription = aws.sns.TopicSubscription(
    f"{product_name}_incoming_mail_topic_subscription",
    topic=incoming_mail_topic.arn,
    protocol="lambda",
    endpoint=store_email_function.arn,
)

incoming_mail_topic_policy = aws.sns.TopicPolicy(
    f"{product_name}_incoming_mail_topic_policy",
    arn=incoming_mail_topic.arn,
    policy=pulumi.Output.all(incoming_mail_topic_arn=incoming_mail_topic.arn).apply(
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
    f"{product_name}_store_email_function_permission",
    action="lambda:InvokeFunction",
    function=store_email_function.arn,
    principal="sns.amazonaws.com",
    source_arn=incoming_mail_topic.arn,
)

create_email_function_role = aws.iam.Role(
    f"{product_name}_create_email_function_role",
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
            name="address_table_policy",
            policy=pulumi.Output.all(address_table_arn=addresses_table.arn).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["dynamodb:PutItem", "dynamodb:GetItem"],
                                "Resource": args["address_table_arn"],
                            },
                        ],
                    }
                )
            ),
        ),
    ],
)

get_emails_list_function_role = aws.iam.Role(
    f"{product_name}_get_emails_list_function_role",
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
            name="EmailsTables",
            policy=pulumi.Output.all(
                emails_table_arn=emails_table.arn,
                addresses_table_arn=addresses_table.arn,
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

get_emails_list_function = aws.lambda_.Function(
    f"{product_name}_get_emails_list_function",
    runtime="python3.10",
    description="Get list of emails for a specific address.",
    handler="get_emails_list_function.lambda_handler",
    role=get_emails_list_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "emails_table_name": emails_table.name,
            "addresses_table_name": addresses_table.name,
        }
    ),
    timeout=30,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)

get_addresses_function = aws.lambda_.Function(
    f"{product_name}_get_addresses_function",
    runtime="python3.10",
    description="Get list of emails address for a specific user.",
    handler="get_addresses_function.lambda_handler",
    role=get_emails_list_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "addresses_table_name": addresses_table.name,
        }
    ),
    timeout=30,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)

post_addresses_function = aws.lambda_.Function(
    f"{product_name}_post_addresses_function",
    runtime="python3.10",
    description="Create email address for a specific user.",
    handler="post_addresses_function.lambda_handler",
    role=get_emails_list_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "addresses_table_name": addresses_table.name,
            "email_domain": email_domain,
        }
    ),
    timeout=30,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)

delete_address_function_role = aws.iam.Role(
    f"{product_name}_delete_address_function_role",
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
            name="EmailsTableGetDeleteItem",
            policy=pulumi.Output.all(
                emails_table_arn=emails_table.arn,
                addresses_table_arn=addresses_table.arn,
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
                            }
                        ],
                    }
                )
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="MailBucketDeleteObject",
            policy=pulumi.Output.all(incoming_mail_bucket_arn=email_bucket.arn).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "s3:DeleteObject",
                                "Resource": f"{args['incoming_mail_bucket_arn']}/*",
                            }
                        ],
                    }
                )
            ),
        ),
    ],
)
delete_address_function = aws.lambda_.Function(
    f"{product_name}_delete_address_function",
    runtime="python3.10",
    description="Delete mailbox",
    handler="delete_address_function.lambda_handler",
    role=delete_address_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "emails_table_name": emails_table.name,
            "addresses_table_name": addresses_table.name,
        }
    ),
    timeout=120,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)

get_email_function_role = aws.iam.Role(
    f"{product_name}_get_email_function_role",
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
            name="EmailsTableGetUpdateItem",
            policy=pulumi.Output.all(
                addresses_table_arn=addresses_table.arn,
                emails_table_arn=emails_table.arn,
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
                        ],
                    }
                )
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="MailBucketGetObject",
            policy=pulumi.Output.all(email_bucket=email_bucket.arn).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "s3:GetObject",
                                "Resource": f"{args['email_bucket']}/*",
                            }
                        ],
                    }
                ),
            ),
        ),
    ],
)
get_email_function = aws.lambda_.Function(
    f"{product_name}_get_email_function",
    runtime="python3.10",
    description="Get contents of a specific messageId.",
    handler="get_email_function.lambda_handler",
    role=get_email_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "emails_table_name": emails_table.name,
            "addresses_table_name": addresses_table.name,
        }
    ),
    timeout=60,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)

delete_email_item_function = aws.lambda_.Function(
    f"{product_name}_delete_email_item_function",
    runtime="python3.10",
    description="Delete email item function",
    handler="delete_email_item_function.lambda_handler",
    role=delete_address_function_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "emails_table_name": emails_table.name,
            "addresses_table_name": addresses_table.name,
        }
    ),
    timeout=30,
    layers=[lambda_layer.arn],
    tracing_config=(
        aws.lambda_.FunctionTracingConfigArgs(mode="Active")
        if xray_enabled.lower() == "true"
        else None
    ),
    code=local_archive,
)
