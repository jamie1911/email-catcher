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

ddb_client = boto3.resource("dynamodb")
table_addresses = ddb_client.Table(os.environ["ADDRESS_TABLE_NAME"])


def address_exists(address: str):
    try:
        response = table_addresses.get_item(Key={"address": address.lower()})
        if "Item" in response:
            item = response["Item"]
            if item["address"]:
                return True
            else:
                return False
        else:
            return False
    except ClientError as e:
        logger.warning("## DynamoDB Client Exception")
        logger.warning(e.response["Error"]["Message"])
        return False


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)

    for record in event["Records"]:
        to_address = record["ses"]["mail"]["destination"][0]
        logger.info("## DESTINATION")
        logger.info(to_address)
        if address_exists(to_address):
            logger.info("## ADDRESS EXISTS, CONTINUE")
            return {"disposition": "CONTINUE"}
        else:
            logger.info("## ADDRESS DOESNT EXIST, STOPPING RULE SET")
            return {"disposition": "STOP_RULE_SET"}
        break
