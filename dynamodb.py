import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import stack, product_name

register_standard_tags(environment=stack)

local_name = f"{product_name}_ddb"

# AddressesTable
table_addresses = aws.dynamodb.Table(
    f"{local_name}_table_addresses",
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
table_emails = aws.dynamodb.Table(
    f"{local_name}_table_emails",
    billing_mode="PAY_PER_REQUEST",
    attributes=[
        aws.dynamodb.TableAttributeArgs(name="destination", type="S"),
        aws.dynamodb.TableAttributeArgs(name="messageId", type="S"),
    ],
    hash_key="destination",
    range_key="messageId",
)
