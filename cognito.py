import pulumi
import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import (
    stack,
    product_name,
    cloudfront_web_domain,
    aws_region,
    disable_public_registration,
    initial_user,
)

register_standard_tags(environment=stack)

local_name = f"{product_name}_cognito"

cognito_user_pool = aws.cognito.UserPool(
    f"{local_name}_user_pool",
    username_attributes=["email"],
    auto_verified_attributes=["email"],
    admin_create_user_config=aws.cognito.UserPoolAdminCreateUserConfigArgs(
        allow_admin_create_user_only=disable_public_registration
    ),
    account_recovery_setting=aws.cognito.UserPoolAccountRecoverySettingArgs(
        recovery_mechanisms=[
            aws.cognito.UserPoolAccountRecoverySettingRecoveryMechanismArgs(
                name="verified_email", priority=1
            )
        ]
    ),
    user_attribute_update_settings=aws.cognito.UserPoolUserAttributeUpdateSettingsArgs(
        attributes_require_verification_before_updates=["email"]
    ),
    opts=pulumi.ResourceOptions(ignore_changes=["schemas"]), # https://github.com/pulumi/pulumi-aws/issues/4158
)

cognito_user_pool_client = aws.cognito.UserPoolClient(
    f"{local_name}_user_pool_client",
    user_pool_id=cognito_user_pool.id,
    callback_urls=[f"https://{cloudfront_web_domain}"],
    logout_urls=[f"https://{cloudfront_web_domain}/logout"],
)

if initial_user.get("enabled", False):
    aws.cognito.User(
        f"{local_name}_user",
        user_pool_id=cognito_user_pool.id,
        username=initial_user["username"],
        temporary_password=initial_user["temporary_password"],
        attributes={"email": initial_user["username"], "email_verified": "true"},
        opts=pulumi.ResourceOptions(depends_on=[cognito_user_pool]),
    )

pulumi.export("cognito_region", aws_region)
pulumi.export("cognito_user_pool_id", cognito_user_pool.id)
pulumi.export("cognito_user_pool_client", cognito_user_pool_client.id)
