import json
import os
import logging

import boto3
from botocore.exceptions import ClientError
from aws_xray_sdk.core import xray_recorder, patch_all

if os.environ.get("XRAY_ENABLED", "false").lower() == "true":
    XRAY_NAME = os.environ.get("XRAY_NAME", "email-catcher")
    xray_recorder.configure(service=XRAY_NAME)
    patch_all()

LOGGING_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOGGING_LEVEL)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["emails_table_name"])


def store_email(email, receipt):
    try:
        table.put_item(
            Item={
                "destination": email["destination"][0],
                "messageId": email["messageId"],
                "timestamp": email["timestamp"],
                "source": email["source"],
                "commonHeaders": email["commonHeaders"],
                "bucketName": receipt["action"]["bucketName"],
                "bucketObjectKey": receipt["action"]["objectKey"],
                "isNew": True,
            }
        )
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)

    message = json.loads(event["Records"][0]["Sns"]["Message"])
    store_email(message["mail"], message["receipt"])
