import json
import pulumi
import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import (
    stack,
    aws_region,
    aws_account_id,
    product_name,
    ses_email_domain,
    log_level,
    xray_enabled,
    LAMBDA_TIMEOUT,
    LAMBDA_PYTHON_VERSION,
)
from common import cw_log_group
from dynamodb import table_addresses, table_emails
from s3 import bucket_emails

register_standard_tags(environment=stack)

local_name = f"{product_name}_lambda"

lambda_code_layer = aws.lambda_.LayerVersion(
    f"{local_name}_code_layer",
    compatible_runtimes=[LAMBDA_PYTHON_VERSION],
    code=pulumi.FileArchive("./code_layer"),
    skip_destroy=False,
    layer_name=f"{product_name}_lambda_code_layer",
)
local_archive = pulumi.FileArchive("./lambda")

lambda_role = aws.iam.Role(
    f"{local_name}_role",
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
                                "Action": [
                                    "dynamodb:UpdateItem",
                                    "dynamodb:GetItem",
                                    "dynamodb:PutItem",
                                    "dynamodb:DeleteItem",
                                    "dynamodb:Scan",
                                    "dynamodb:Query",
                                ],
                                "Resource": [
                                    args["emails_table_arn"],
                                    args["address_table_arn"],
                                    f"{args['emails_table_arn']}/*",
                                    f"{args['address_table_arn']}/*",
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "s3:GetObject*",
                                    "s3:PutObject*",
                                    "s3:DeleteObject*",
                                    "s3:ListBucket",
                                ],
                                "Resource": [
                                    args["email_bucket_arn"],
                                    f"{args['email_bucket_arn']}/*",
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["bedrock:InvokeModel"],
                                "Resource": ["*"],
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "states:StartExecution",
                                ],
                                "Resource": [
                                    f"arn:aws:states:{aws_region}:{aws_account_id}:stateMachine:{local_name}_sm_incoming_mail"
                                ],
                            },
                        ],
                    }
                )
            ),
        ),
    ],
)

lambda_check_incoming_address = aws.lambda_.Function(
    f"{local_name}_check_incoming_address",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Invoked by SES to check if email address exists.",
    handler="ses_check_incoming_address_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

aws.lambda_.Permission(
    f"{local_name}_check_incoming_address_permission",
    action="lambda:InvokeFunction",
    function=lambda_check_incoming_address.arn,
    principal="ses.amazonaws.com",
    source_account=aws_account_id,
)

lambda_store_email = aws.lambda_.Function(
    f"{local_name}_store_email",
    runtime=LAMBDA_PYTHON_VERSION,
    memory_size=256,
    description="Incoming email topic subscriber to store emails and s3 object locations in db",
    handler="sm_store_email_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_start_incoming_mail = aws.lambda_.Function(
    f"{local_name}_start_incoming_mail",
    runtime=LAMBDA_PYTHON_VERSION,
    memory_size=128,
    description="SNS starts incoming email state machine",
    handler="sns_start_incoming_mail_sm_function.lambda_handler",
    role=lambda_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "INCOMING_MAIL_STATE_MACHINE_ARN": f"arn:aws:states:{aws_region}:{aws_account_id}:stateMachine:{local_name}_sm_incoming_mail",
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_sns_check_incoming_address_topic = aws.sns.Topic(
    f"{local_name}_sns_check_incoming_address_topic",
    display_name="Store Successful Incoming Email Topic",
    tracing_config="Active" if xray_enabled.lower() == "true" else None,
)
lambda_sns_incoming_mail_topic_subscription = aws.sns.TopicSubscription(
    f"{local_name}_sns_check_incoming_address_topic_subscription",
    topic=lambda_sns_check_incoming_address_topic.arn,
    protocol="lambda",
    endpoint=lambda_start_incoming_mail.arn,
)

lambda_sns_incoming_mail_topic_policy = aws.sns.TopicPolicy(
    f"{local_name}_sns_check_incoming_address_topic_policy",
    arn=lambda_sns_check_incoming_address_topic.arn,
    policy=pulumi.Output.all(
        lambda_sns_check_incoming_address_topic_arn=lambda_sns_check_incoming_address_topic.arn
    ).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "sns:Publish",
                        "Resource": args["lambda_sns_check_incoming_address_topic_arn"],
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
    f"{local_name}_sns_start_incoming_mail_state_machine_permission",
    action="lambda:InvokeFunction",
    function=lambda_start_incoming_mail.arn,
    principal="sns.amazonaws.com",
    source_arn=lambda_sns_check_incoming_address_topic.arn,
)

lambda_get_emails = aws.lambda_.Function(
    f"{local_name}_get_emails",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Gets the list of emails for a specific address",
    handler="api_get_emails_list_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_get_addresses = aws.lambda_.Function(
    f"{local_name}_get_addresses",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Gets the list of email addresses for a specific user",
    handler="api_get_addresses_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_post_addresses = aws.lambda_.Function(
    f"{local_name}_post_addresses",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Create email address for a specific user",
    handler="api_post_addresses_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_delete_address = aws.lambda_.Function(
    f"{local_name}_delete_address",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Delete email address for a specific user",
    handler="api_delete_address_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_delete_email_item = aws.lambda_.Function(
    f"{local_name}_delete_email_item",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Delete email item from an address for a specific user",
    handler="api_delete_email_item_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_get_email = aws.lambda_.Function(
    f"{local_name}_get_email",
    runtime=LAMBDA_PYTHON_VERSION,
    description="Get contents of a specific email for a user",
    handler="api_get_email_function.lambda_handler",
    role=lambda_role.arn,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_store_attachments = aws.lambda_.Function(
    f"{local_name}_store_attachments",
    runtime=LAMBDA_PYTHON_VERSION,
    memory_size=256,
    description="Extract attachments from incoming emails",
    handler="sm_store_attachments_function.lambda_handler",
    role=lambda_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)

lambda_summarize_email = aws.lambda_.Function(
    f"{local_name}_summarize_email",
    runtime=LAMBDA_PYTHON_VERSION,
    memory_size=512,
    description="Summarize incoming emails",
    handler="sm_summarize_email_function.lambda_handler",
    role=lambda_role.arn,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "LOG_LEVEL": log_level,
            "XRAY_ENABLED": xray_enabled,
            "XRAY_NAME": product_name,
            "EMAILS_TABLE_NAME": table_emails.name,
            "ADDRESS_TABLE_NAME": table_addresses.name,
        }
    ),
    timeout=LAMBDA_TIMEOUT + 120,
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
        log_group=cw_log_group.name,
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)


incoming_mail_state_machine_role = aws.iam.Role(
    f"{local_name}_sfn",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "states.amazonaws.com"},
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
                                "logs:CreateLogDelivery",
                                "logs:CreateLogStream",
                                "logs:GetLogDelivery",
                                "logs:UpdateLogDelivery",
                                "logs:DeleteLogDelivery",
                                "logs:ListLogDeliveries",
                                "logs:PutLogEvents",
                                "logs:PutResourcePolicy",
                                "logs:DescribeResourcePolicies",
                                "logs:DescribeLogGroups",
                            ],
                            "Resource": "*",
                        }
                    ],
                }
            ),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="access_policy",
            policy=pulumi.Output.all(
                lambda_store_email_arn=lambda_store_email.arn,
                lambda_store_attachments_arn=lambda_store_attachments.arn,
                lambda_summarize_email_arn=lambda_summarize_email.arn,
            ).apply(
                lambda args: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Action": ["lambda:InvokeFunction"],
                                "Resource": [
                                    args["lambda_store_email_arn"],
                                    args["lambda_store_attachments_arn"],
                                    args["lambda_summarize_email_arn"],
                                ],
                                "Effect": "Allow",
                            }
                        ],
                    }
                )
            ),
        ),
    ],
)

state_machine_incoming_mail_definition = pulumi.Output.all(
    lambda_store_email_arn=lambda_store_email.arn,
    lambda_store_attachments_arn=lambda_store_attachments.arn,
    lambda_summarize_email_arn=lambda_summarize_email.arn,
).apply(
    lambda args: json.dumps(
        {
            "Comment": "Email Processing",
            "StartAt": "Store Email",
            "States": {
                "Store Email": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::lambda:invoke",
                    "Parameters": {
                        "Payload.$": "$",
                        "FunctionName": f"{args['lambda_store_email_arn']}",
                    },
                    "Retry": [
                        {
                            "ErrorEquals": [
                                "Lambda.Unknown",
                                "Lambda.ServiceException",
                                "Lambda.AWSLambdaException",
                                "Lambda.SdkClientException",
                                "Lambda.TooManyRequestsException",
                            ],
                            "IntervalSeconds": 1,
                            "MaxAttempts": 3,
                            "BackoffRate": 2,
                        }
                    ],
                    "Next": "Extract Attachments",
                    "OutputPath": "$.Payload",
                },
                "Extract Attachments": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::lambda:invoke",
                    "Parameters": {
                        "Payload.$": "$",
                        "FunctionName": f"{args['lambda_store_attachments_arn']}",
                    },
                    "Retry": [
                        {
                            "ErrorEquals": [
                                "Lambda.Unknown",
                                "Lambda.ServiceException",
                                "Lambda.AWSLambdaException",
                                "Lambda.SdkClientException",
                                "Lambda.TooManyRequestsException",
                            ],
                            "IntervalSeconds": 1,
                            "MaxAttempts": 3,
                            "BackoffRate": 2,
                        }
                    ],
                    "Next": "Summarize Email",
                    "OutputPath": "$.Payload",
                },
                "Summarize Email": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::lambda:invoke",
                    "Parameters": {
                        "Payload.$": "$",
                        "FunctionName": f"{args['lambda_summarize_email_arn']}",
                    },
                    "Retry": [
                        {
                            "ErrorEquals": [
                                "Lambda.Unknown",
                                "Lambda.ServiceException",
                                "Lambda.AWSLambdaException",
                                "Lambda.SdkClientException",
                                "Lambda.TooManyRequestsException",
                            ],
                            "IntervalSeconds": 1,
                            "MaxAttempts": 3,
                            "BackoffRate": 2,
                        }
                    ],
                    "End": True,
                    "OutputPath": "$.Payload",
                },
            },
        }
    )
)


state_machine_incoming_mail = aws.sfn.StateMachine(
    f"{local_name}_sm_incoming_mail",
    name=f"{local_name}_sm_incoming_mail",
    role_arn=incoming_mail_state_machine_role.arn,
    type="EXPRESS",
    definition=state_machine_incoming_mail_definition,
    logging_configuration=aws.sfn.StateMachineLoggingConfigurationArgs(
        log_destination=pulumi.Output.all(cloudwatch_arn=cw_log_group.arn).apply(
            lambda arns: f"{arns['cloudwatch_arn']}:*"
        ),
        include_execution_data=True,
        level="ALL",
    ),
    tracing_configuration=(
        aws.sfn.StateMachineTracingConfigurationArgs(enabled=True)
        if xray_enabled.lower() == "true"
        else None
    ),
    opts=pulumi.ResourceOptions(depends_on=[cw_log_group]),
)
