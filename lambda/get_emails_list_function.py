import os
import logging

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from aws_xray_sdk.core import xray_recorder, patch_all

from util import check_access, create_response, get_user_sub_from_event


if os.environ.get("XRAY_ENABLED", "false").lower() == "true":
    XRAY_NAME = os.environ.get("XRAY_NAME", "email-catcher")
    xray_recorder.configure(service=XRAY_NAME)
    patch_all()

LOGGING_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOGGING_LEVEL)

ddb_client = boto3.resource("dynamodb")
table_addresses = ddb_client.Table(os.environ["ADDRESS_TABLE_NAME"])
table_emails = ddb_client.Table(os.environ["EMAILS_TABLE_NAME"])


def get_emails(destination, user_sub):
    try:
        if check_access(table_addresses, user_sub, destination):
            filtering_exp = Key("destination").eq(destination)
            response = table_emails.query(KeyConditionExpression=filtering_exp)
            items = response["Items"]
            sorted_items = sorted(items, key=lambda x: x["timestamp"], reverse=True)
            return sorted_items
        else:
            return []
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
        destination = event["pathParameters"]["addressId"]
        user_sub = get_user_sub_from_event(event)
        items = get_emails(destination, user_sub)

        return create_response(status_code=200, body=items)
    except Exception as e:
        logger.exception(e)
        return create_response(status_code=500, body=e)
