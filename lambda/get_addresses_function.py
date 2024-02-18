import os
import logging

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from aws_xray_sdk.core import xray_recorder, patch_all


from util import create_response, get_user_sub_from_event

if os.environ.get("XRAY_ENABLED", "false").lower() == "true":
    XRAY_NAME = os.environ.get("XRAY_NAME", "email-catcher")
    xray_recorder.configure(service=XRAY_NAME)
    patch_all()

LOGGING_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOGGING_LEVEL)

dynamodb = boto3.resource("dynamodb")
ddb_table = dynamodb.Table(os.environ["addresses_table_name"])


def get_emails_addresses(user_sub):
    try:
        filtering_exp = Key("user_sub").eq(user_sub)
        response = ddb_table.query(
            IndexName="UserIndex", KeyConditionExpression=filtering_exp
        )
        return response["Items"]
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])
        raise e.response["Error"]["Message"]


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)
    try:
        user_sub = get_user_sub_from_event(event)
        logger.info("user_sub getting addresses: %s", user_sub)
        items = get_emails_addresses(user_sub)
        return create_response(status_code=200, body=items)
    except Exception as e:
        logger.error("exception getting addresses: %s", e)
        return create_response(status_code=500, body=e)
