import sys
import pulumi_aws as aws

sys.path.insert(0, "../../../../")

from shared.aws.tagging import register_standard_tags
from config import stack, product_name

register_standard_tags(environment=stack)

# AddressesTable
addresses_table = aws.dynamodb.Table(
    f"{product_name}_addresses_table",
    name=f"{product_name}_addresses",
    attributes=[
        aws.dynamodb.TableAttributeArgs(name="address", type="S"),
        aws.dynamodb.TableAttributeArgs(name="user_sub", type="S"),
    ],
    hash_key="address",
    global_secondary_indexes=[
        aws.dynamodb.TableGlobalSecondaryIndexArgs(
            name="UserIndex",  # Name of the GSI
            hash_key="user_sub",  # Set address as the hash key for GSI
            projection_type="ALL",  # Choose the projection type as needed
        ),
    ],
    billing_mode="PAY_PER_REQUEST",
)

# EmailsTable
emails_table = aws.dynamodb.Table(
    f"{product_name}_emails_table",
    name=f"{product_name}_emails",
    billing_mode="PAY_PER_REQUEST",
    attributes=[
        aws.dynamodb.TableAttributeArgs(name="destination", type="S"),
        aws.dynamodb.TableAttributeArgs(name="messageId", type="S"),
    ],
    hash_key="destination",
    range_key="messageId",
)
