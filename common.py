import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import (
    stack,
    product_name,
)

register_standard_tags(environment=stack)

local_name = f"{product_name}_common"

cw_log_group = aws.cloudwatch.LogGroup(
    f"{local_name}_cw_log_group", retention_in_days=7, skip_destroy=False
)
