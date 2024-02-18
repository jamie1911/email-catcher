import sys
import pulumi
import pulumi_aws as aws

sys.path.insert(0, "../../../../")

from shared.aws.tagging import register_standard_tags
from config import (
    stack,
    product_name,
    cloudfront_domain,
    aws_region,
    disable_public_registration,
)

register_standard_tags(environment=stack)

user_pool = aws.cognito.UserPool(
    f"{product_name}_user_pool",
    username_attributes=["email"],
    auto_verified_attributes=["email"],
    admin_create_user_config=aws.cognito.UserPoolAdminCreateUserConfigArgs(
        allow_admin_create_user_only=disable_public_registration
    ),
)

user_pool_client = aws.cognito.UserPoolClient(
    f"{product_name}_user_pool_client",
    user_pool_id=user_pool.id,
    callback_urls=[f"https://{cloudfront_domain}"],
    logout_urls=[f"https://{cloudfront_domain}/logout"],
)

pulumi.export("cognito_region", aws_region)
pulumi.export("cognito_user_pool_id", user_pool.id)
pulumi.export("cognito_user_pool_client", user_pool_client.id)
