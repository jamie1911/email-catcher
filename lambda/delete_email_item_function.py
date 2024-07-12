import os
import logging

import boto3
from botocore.exceptions import ClientError
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
s3 = boto3.client("s3")

table_addresses = ddb_client.Table(os.environ["ADDRESS_TABLE_NAME"])
table_emails = ddb_client.Table(os.environ["EMAILS_TABLE_NAME"])


def get_email_item(destination, messageId):
    result = None
    try:
        response = table_emails.get_item(
            Key={"destination": destination, "messageId": messageId}
        )
        if "Item" in response:
            result = response["Item"]
            return result
        else:
            return result
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])
        raise e.response["Error"]["Message"]


def delete_email_item(destination, messageId):
    try:
        table_emails.delete_item(
            Key={"destination": destination, "messageId": messageId}
        )
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
        messageId = event["pathParameters"]["messageId"]
        user_sub = get_user_sub_from_event(event)

        if check_access(table_addresses, user_sub, destination):
            email_file = get_email_item(destination, messageId)
            if email_file is not None:
                s3.delete_object(
                    Bucket=email_file["bucketName"], Key=email_file["bucketObjectKey"]
                )
                delete_email_item(destination, messageId)
                return create_response(
                    status_code=200,
                    body=None,
                )
            else:
                return create_response(
                    status_code=404,
                    body=None,
                )
        else:
            return create_response(
                status_code=401,
                body=None,
            )
    except Exception as e:
        logger.exception(e)
        return create_response(
            status_code=500,
            body=e,
        )
