import json
import os
import logging
import re

import boto3
from botocore.exceptions import ClientError
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
addresses_table = dynamodb.Table(os.environ["addresses_table_name"])
email_domain = os.environ["email_domain"]


def address_exists(address: str):
    try:
        response = addresses_table.get_item(Key={"address": address.lower()})
        if "Item" in response:
            item = response["Item"]
            if item["address"]:
                return True
            else:
                return False
        else:
            return False
    except ClientError as e:
        logger.info("## DynamoDB Client Exception")
        logger.info(e.response["Error"]["Message"])
        return False


def create_address(address: str, user_sub: str, summarize_emails: bool = False):
    try:
        addresses_table.put_item(
            Item={
                "address": address.lower(),
                "user_sub": user_sub,
                "summarize_emails": summarize_emails,
            }
        )
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])
        raise e.response["Error"]["Message"]


def validate_email(address):
    valid = False
    # Do some basic regex validation
    match = re.match(
        "^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,4})$", address
    )
    if match != None:
        logger.info(f"{address} does not follow the email pattern")
        domain = address.split("@")[-1]
        if domain == email_domain:
            valid = True
            logger.info(f"{address} is part of a valid email domain")
        else:
            logger.info(f"{address} is not part of a valid domain")
    return valid


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)
    try:
        user_sub = get_user_sub_from_event(event)

        body = json.loads(event["body"])
        new_address = body.get("new_address", None)
        summarize_emails = body.get("summarize_emails", None)

        if validate_email(new_address):
            if address_exists(new_address):
                message = "email address already exists, please use a different address"
                logger.info(f"{new_address} already exists")
                return create_response(status_code=400, body=message)
            else:
                logger.info(f"creating {new_address}")
                create_address(new_address, user_sub, summarize_emails)
                message = "email address created"
                return create_response(status_code=201, body=message)
        else:
            return create_response(status_code=400, body="Invalid request data")
    except Exception as e:
        return create_response(status_code=500, body=e)
