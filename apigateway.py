import json
import uuid
import pulumi
import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import stack, product_name, xray_enabled
from aws_lambda import (
    lambda_get_emails,
    lambda_get_email,
    lambda_get_addresses,
    lambda_post_addresses,
    lambda_delete_email_item,
    lambda_delete_address,
)
from cognito import cognito_user_pool

register_standard_tags(environment=stack)

local_name = f"{product_name}_api"

api_role = aws.iam.Role(
    f"{local_name}_role",
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
                lambda_get_emails=lambda_get_emails.arn,
                lambda_get_email=lambda_get_email.arn,
                lambda_get_addresses=lambda_get_addresses.arn,
                lambda_post_addresses=lambda_post_addresses.arn,
                lambda_delete_email_item=lambda_delete_email_item.arn,
                lambda_delete_address=lambda_delete_address.arn,
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
                                "Resource": "arn:aws:logs:*:*:*",
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["lambda:InvokeFunction"],
                                "Resource": [
                                    args["lambda_get_emails"],
                                    args["lambda_get_email"],
                                    args["lambda_get_addresses"],
                                    args["lambda_post_addresses"],
                                    args["lambda_delete_email_item"],
                                    args["lambda_delete_address"],
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
    f"{local_name}",
    description=f"Disposable emails API for {product_name}",
    endpoint_configuration=aws.apigateway.RestApiEndpointConfigurationArgs(
        types="REGIONAL"
    ),
)
authorizer = aws.apigateway.Authorizer(
    f"{local_name}_authorizer",
    rest_api=api.id,
    type="COGNITO_USER_POOLS",
    provider_arns=[cognito_user_pool.arn],
    identity_source="method.request.header.Authorization",
)

####addresses####
api_addresses_resource = aws.apigateway.Resource(
    f"{local_name}_addresses_resource",
    parent_id=api.root_resource_id,
    path_part="addresses",
    rest_api=api.id,
)
api_addresses_get_method = aws.apigateway.Method(
    f"{local_name}_addresses_get_method",
    http_method="GET",
    resource_id=api_addresses_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_addresses_get_method_integration = aws.apigateway.Integration(
    f"{local_name}_addresses_get_method_integration",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_get_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=lambda_get_addresses.invoke_arn,
    credentials=api_role.arn,
)
api_addresses_option_method = aws.apigateway.Method(
    f"{local_name}_addresses_option_method",
    http_method="OPTIONS",
    resource_id=api_addresses_resource.id,
    rest_api=api.id,
    request_models={"application/json": "Empty"},
    authorization="NONE",
)
api_addresses_option_method_response = aws.apigateway.MethodResponse(
    f"{local_name}_addresses_option_method_response",
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
    f"{local_name}_addresses_option_method_integration",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_option_method.http_method,
    type="MOCK",
    request_templates={"application/json": '{"statusCode": 200}'},
    passthrough_behavior="WHEN_NO_MATCH",
    credentials=api_role.arn,
)
api_addresses_option_method_integration_response = aws.apigateway.IntegrationResponse(
    f"{local_name}_addresses_option_method_integration_response",
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
    f"{local_name}_addresses_post_method",
    http_method="POST",
    resource_id=api_addresses_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_addresses_post_method_integration = aws.apigateway.Integration(
    f"{local_name}_addresses_post_method_integration",
    rest_api=api.id,
    resource_id=api_addresses_resource.id,
    http_method=api_addresses_post_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=lambda_post_addresses.invoke_arn,
    credentials=api_role.arn,
)


###address messages###
api_address_resource = aws.apigateway.Resource(
    f"{local_name}_address_resource",
    parent_id=api_addresses_resource.id,
    path_part="{addressId}",
    rest_api=api.id,
)
api_address_delete_method = aws.apigateway.Method(
    f"{local_name}_address_delete_method",
    http_method="DELETE",
    resource_id=api_address_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_address_delete_method_integration = aws.apigateway.Integration(
    f"{local_name}_address_delete_method_integration",
    rest_api=api.id,
    resource_id=api_address_resource.id,
    http_method=api_address_delete_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=lambda_delete_address.invoke_arn,
    credentials=api_role.arn,
)
api_address_get_method = aws.apigateway.Method(
    f"{local_name}_address_get_method",
    http_method="GET",
    resource_id=api_address_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_address_get_method_integration = aws.apigateway.Integration(
    f"{local_name}_address_get_method_integration",
    rest_api=api.id,
    resource_id=api_address_resource.id,
    http_method=api_address_get_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=lambda_get_emails.invoke_arn,
    credentials=api_role.arn,
)
api_address_option_method = aws.apigateway.Method(
    f"{local_name}_address_option_method",
    http_method="OPTIONS",
    resource_id=api_address_resource.id,
    rest_api=api.id,
    request_models={"application/json": "Empty"},
    authorization="NONE",
)
api_address_option_method_response = aws.apigateway.MethodResponse(
    f"{local_name}_address_option_method_response",
    rest_api=api.id,
    resource_id=api_address_resource.id,
    http_method=api_address_option_method.http_method,
    status_code="200",
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": True,
        "method.response.header.Access-Control-Allow-Methods": True,
        "method.response.header.Access-Control-Allow-Origin": True,
        "method.response.header.Access-Control-Allow-Credentials": True,
    },
)
api_address_option_method_integration = aws.apigateway.Integration(
    f"{local_name}_address_option_method_integration",
    rest_api=api.id,
    resource_id=api_address_resource.id,
    http_method=api_address_option_method.http_method,
    type="MOCK",
    request_templates={"application/json": '{"statusCode": 200}'},
    passthrough_behavior="WHEN_NO_MATCH",
    credentials=api_role.arn,
)
api_address_option_method_integration_response = aws.apigateway.IntegrationResponse(
    f"{local_name}_address_option_method_integration_response",
    status_code="200",
    rest_api=api.id,
    resource_id=api_address_resource.id,
    http_method=api_address_option_method.http_method,
    response_parameters={
        "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
        "method.response.header.Access-Control-Allow-Methods": "'GET,OPTIONS,DELETE'",
        "method.response.header.Access-Control-Allow-Origin": "'*'",
    },
    response_templates={"application/json": ""},
    opts=pulumi.ResourceOptions(parent=api_address_option_method_integration),
)

###address message items###
api_message_resource = aws.apigateway.Resource(
    f"{local_name}_message_resource",
    parent_id=api_address_resource.id,
    path_part="{messageId}",
    rest_api=api.id,
)

api_message_get_method = aws.apigateway.Method(
    f"{local_name}_message_get_method",
    http_method="GET",
    resource_id=api_message_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_message_get_method_integration = aws.apigateway.Integration(
    f"{local_name}_message_get_method_integration",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_get_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=lambda_get_email.invoke_arn,
    credentials=api_role.arn,
)

api_message_delete_method = aws.apigateway.Method(
    f"{local_name}_message_delete_method",
    http_method="DELETE",
    resource_id=api_message_resource.id,
    rest_api=api.id,
    authorizer_id=authorizer.id,
    authorization="COGNITO_USER_POOLS",
)
api_message_delete_method_integration = aws.apigateway.Integration(
    f"{local_name}_message_delete_method_integration",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_delete_method.http_method,
    integration_http_method="POST",
    type="AWS_PROXY",
    uri=lambda_delete_email_item.invoke_arn,
    credentials=api_role.arn,
)

api_message_option_method = aws.apigateway.Method(
    f"{local_name}_message_option_method",
    http_method="OPTIONS",
    resource_id=api_message_resource.id,
    rest_api=api.id,
    request_models={"application/json": "Empty"},
    authorization="NONE",
)
api_message_option_method_response = aws.apigateway.MethodResponse(
    f"{local_name}_message_option_method_response",
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
    f"{local_name}_message_option_method_integration",
    rest_api=api.id,
    resource_id=api_message_resource.id,
    http_method=api_message_option_method.http_method,
    type="MOCK",
    request_templates={"application/json": '{"statusCode": 200}'},
    passthrough_behavior="WHEN_NO_MATCH",
)
api_message_option_method_integration_response = aws.apigateway.IntegrationResponse(
    f"{local_name}_message_option_method_integration_response",
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
api_deployment = aws.apigateway.Deployment(
    f"{local_name}_deployment",
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
            api_address_get_method,
            api_address_get_method_integration,
            api_address_option_method,
            api_address_option_method_integration,
            api_address_option_method_integration_response,
            api_address_delete_method,
            api_address_delete_method_integration,
            api_message_get_method,
            api_message_get_method_integration,
            api_message_option_method,
            api_message_option_method_integration,
            api_message_option_method_integration_response,
            api_message_delete_method,
            api_message_delete_method_integration,
        ]
    ),
)

api_stage = aws.apigateway.Stage(
    f"{local_name}_stage",
    deployment=api_deployment.id,
    rest_api=api.id,
    stage_name="v0",
    description="API Stage v0",
    xray_tracing_enabled=True if xray_enabled.lower() == "true" else None,
    opts=pulumi.ResourceOptions(
        depends_on=[api_deployment],
    ),
)

pulumi.export("api_gateway_url", api_stage.invoke_url)
