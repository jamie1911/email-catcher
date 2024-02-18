import json
import uuid
import sys
import pulumi
import pulumi_aws as aws

sys.path.insert(0, "../../../../")

from shared.aws.tagging import register_standard_tags
from config import stack, product_name, xray_enabled
from aws_lambda import (
    get_emails_list_function,
    get_email_function,
    get_addresses_function,
    post_addresses_function,
    delete_email_item_function,
    delete_address_function,
)
from cognito import user_pool

register_standard_tags(environment=stack)

api_role = aws.iam.Role(
    f"{product_name}_api_role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "apigateway.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="access",
            policy=pulumi.Output.all(
                get_emails_list_function=get_emails_list_function.arn,
                get_email_function=get_email_function.arn,
                get_addresses_function=get_addresses_function.arn,
                post_addresses_function=post_addresses_function.arn,
                delete_email_item_function=delete_email_item_function.arn,
                delete_address_function=delete_address_function.arn,
            ).apply(
                lambda args: json.dumps(
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
                                "Resource": ["*"],
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["lambda:*"],
                                "Resource": [
                                    args["get_emails_list_function"],
                                    args["get_email_function"],
                                    args["get_addresses_function"],
                                    args["post_addresses_function"],
                                    args["delete_email_item_function"],
                                    args["delete_address_function"],
                                ],
                            },
                        ],
                    }
                ),
            ),
        ),
    ],
)

api = aws.apigateway.RestApi(
    f"{product_name}_api",
    name=f"{product_name}_api",
    description=f"Disposable emails API for {product_name}",
    endpoint_configuration=aws.apigateway.RestApiEndpointConfigurationArgs(
        types="REGIONAL"
    ),
)
authorizer = aws.apigateway.Authorizer(
    f"{product_name}_api_authorizer",
    rest_api=api.id,  # Reference to the Rest API ID
    name=f"{product_name}_api_authorizer",
    type="COGNITO_USER_POOLS",
    provider_arns=[user_pool.arn],  # Reference to the User Pool ARN
    identity_source="method.request.header.Authorization",
)

####addresses####
api_addresses_resource = aws.apigateway.Resource(
    f"{product_name}_api_addresses_resource",
    parent_id=api.root_resource_id,
    path_part="addresses",
    rest_api=api.id,
)
api_addresses_get_method = aws.apigateway.Method(
    f"{product_name}_api_addresses_get_method",
    http_method="GET",
    resource_id=api_addresses_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_addresses_get_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_addresses_get_method_integration",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_get_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=get_addresses_function.invoke_arn,
    credentials=api_role.arn,
)
api_addresses_option_method = aws.apigateway.Method(
    f"{product_name}_api_addresses_option_method",
    http_method="OPTIONS",
    resource_id=api_addresses_resource.id,
    rest_api=api.id,
    request_models={"application/json": "Empty"},
    authorization="NONE",
)
api_addresses_option_method_response = aws.apigateway.MethodResponse(
    f"{product_name}_api_addresses_option_method_response",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_option_method.http_method,
    status_code="200",
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": True,
        "method.response.header.Access-Control-Allow-Methods": True,
        "method.response.header.Access-Control-Allow-Origin": True,
        "method.response.header.Access-Control-Allow-Credentials": True,
    },
)
api_addresses_option_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_addresses_option_method_integration",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_option_method.http_method,
    type="MOCK",
    request_templates={"application/json": '{"statusCode": 200}'},
    passthrough_behavior="WHEN_NO_MATCH",
    credentials=api_role.arn,
)
api_addresses_option_method_integration_response = aws.apigateway.IntegrationResponse(
    f"{product_name}_api_addresses_option_method_integration_response",
    status_code="200",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_option_method.http_method,
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
        "method.response.header.Access-Control-Allow-Methods": "'GET,OPTIONS'",
        "method.response.header.Access-Control-Allow-Origin": "'*'",
    },
    response_templates={"application/json": ""},
    opts=pulumi.ResourceOptions(parent=api_addresses_option_method_integration),
)
api_addresses_post_method = aws.apigateway.Method(
    f"{product_name}_api_addresses_post_method",
    http_method="POST",
    resource_id=api_addresses_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_addresses_post_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_addresses_post_method_integration",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_post_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=post_addresses_function.invoke_arn,
    credentials=api_role.arn,
)


###emails###
api_emails_resource = aws.apigateway.Resource(
    f"{product_name}_api_emails_resource",
    parent_id=api_addresses_resource.id,
    path_part="{addressId}",
    rest_api=api.id,
)
# DELETE
api_addresses_delete_method = aws.apigateway.Method(
    f"{product_name}_api_addresses_delete_method",
    http_method="DELETE",
    resource_id=api_emails_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_addresses_delete_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_addresses_delete_method_integration",
    rest_api=api.id,
    resource_id=api_emails_resource.id,
    http_method=api_addresses_delete_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=delete_address_function.invoke_arn,
    credentials=api_role.arn,
)

api_emails_get_method = aws.apigateway.Method(
    f"{product_name}_api_emails_get_method",
    http_method="GET",
    resource_id=api_emails_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_emails_get_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_emails_get_method_integration",
    rest_api=api.id,
    resource_id=api_emails_resource.id,
    http_method=api_emails_get_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=get_emails_list_function.invoke_arn,
    credentials=api_role.arn,
)

api_emails_option_method = aws.apigateway.Method(
    f"{product_name}_api_emails_option_method",
    http_method="OPTIONS",
    resource_id=api_emails_resource.id,
    rest_api=api.id,
    request_models={"application/json": "Empty"},
    authorization="NONE",
)
api_emails_option_method_response = aws.apigateway.MethodResponse(
    f"{product_name}_api_emails_option_method_response",
    rest_api=api.id,
    resource_id=api_emails_resource.id,
    http_method=api_emails_option_method.http_method,
    status_code="200",
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": True,
        "method.response.header.Access-Control-Allow-Methods": True,
        "method.response.header.Access-Control-Allow-Origin": True,
        "method.response.header.Access-Control-Allow-Credentials": True,
    },
)
api_emails_option_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_emails_option_method_integration",
    rest_api=api.id,
    resource_id=api_emails_resource.id,
    http_method=api_emails_option_method.http_method,
    type="MOCK",
    request_templates={"application/json": '{"statusCode": 200}'},
    passthrough_behavior="WHEN_NO_MATCH",
    credentials=api_role.arn,
)
api_emails_option_method_integration_response = aws.apigateway.IntegrationResponse(
    f"{product_name}_api_emails_option_method_integration_response",
    status_code="200",
    rest_api=api.id,
    resource_id=api_emails_resource.id,
    http_method=api_emails_option_method.http_method,
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
        "method.response.header.Access-Control-Allow-Methods": "'GET,OPTIONS,DELETE'",
        "method.response.header.Access-Control-Allow-Origin": "'*'",
    },
    response_templates={"application/json": ""},
    opts=pulumi.ResourceOptions(parent=api_emails_option_method_integration),
)


###email items###
api_message_resource = aws.apigateway.Resource(
    f"{product_name}_api_message_resource",
    parent_id=api_emails_resource.id,
    path_part="{messageId}",
    rest_api=api.id,
)

api_message_get_method = aws.apigateway.Method(
    f"{product_name}_api_message_get_method",
    http_method="GET",
    resource_id=api_message_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_message_get_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_message_get_method_integration",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_get_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=get_email_function.invoke_arn,
    credentials=api_role.arn,
)

api_message_delete_method = aws.apigateway.Method(
    f"{product_name}_api_message_delete_method",
    http_method="DELETE",
    resource_id=api_message_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_message_delete_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_message_delete_method_integration",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_delete_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=delete_email_item_function.invoke_arn,
    credentials=api_role.arn,
)

api_message_option_method = aws.apigateway.Method(
    f"{product_name}_api_message_option_method",
    http_method="OPTIONS",
    resource_id=api_message_resource.id,
    rest_api=api.id,
    request_models={"application/json": "Empty"},
    authorization="NONE",
)
api_message_option_method_response = aws.apigateway.MethodResponse(
    f"{product_name}_api_message_option_method_response",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_option_method.http_method,
    status_code="200",
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": True,
        "method.response.header.Access-Control-Allow-Methods": True,
        "method.response.header.Access-Control-Allow-Origin": True,
        "method.response.header.Access-Control-Allow-Credentials": True,
    },
)
api_message_option_method_integration = aws.apigateway.Integration(
    f"{product_name}_api_message_option_method_integration",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_option_method.http_method,
    type="MOCK",
    request_templates={"application/json": '{"statusCode": 200}'},
    passthrough_behavior="WHEN_NO_MATCH",
)
api_message_option_method_integration_response = aws.apigateway.IntegrationResponse(
    f"{product_name}_api_message_option_method_integration_response",
    status_code="200",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_option_method.http_method,
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
        "method.response.header.Access-Control-Allow-Methods": "'GET,DELETE,OPTIONS'",
        "method.response.header.Access-Control-Allow-Origin": "'*'",
    },
    response_templates={"application/json": ""},
    opts=pulumi.ResourceOptions(parent=api_message_option_method_integration),
)

# API Gateway Stage and Deployment
api_stage_deployment = aws.apigateway.Deployment(
    f"{product_name}_api_stage_deployment",
    rest_api=api.id,
    triggers={
        "redeployment": str(uuid.uuid4()),
    },
    opts=pulumi.ResourceOptions(
        depends_on=[
            api_addresses_get_method,
            api_addresses_get_method_integration,
            api_addresses_option_method,
            api_addresses_option_method_integration,
            api_addresses_option_method_integration_response,
            api_emails_get_method,
            api_emails_get_method_integration,
            api_emails_option_method,
            api_emails_option_method_integration,
            api_emails_option_method_integration_response,
            api_message_get_method,
            api_message_get_method_integration,
            api_message_option_method,
            api_message_option_method_integration,
            api_message_option_method_integration_response,
            api_message_delete_method,
            api_message_delete_method_integration,
            api_addresses_delete_method,
            api_addresses_delete_method_integration,
        ]
    ),
)

api_stage = aws.apigateway.Stage(
    f"{product_name}_api_stage",
    deployment=api_stage_deployment.id,
    rest_api=api.id,
    stage_name="v0",
    description="API Stage v0",
    xray_tracing_enabled=True if xray_enabled.lower() == "true" else None,
    opts=pulumi.ResourceOptions(
        depends_on=[api_stage_deployment],
    ),
)

pulumi.export("api_gateway_url", api_stage.invoke_url)
