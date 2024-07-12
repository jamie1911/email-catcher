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
s3 = boto3.client("s3")

table_addresses = ddb_client.Table(os.environ["ADDRESS_TABLE_NAME"])
table_emails = ddb_client.Table(os.environ["EMAILS_TABLE_NAME"])


def delete_object(bucket_name, object_name):
    """Delete an object from an S3 bucket

    :param bucket_name: string
    :param object_name: string
    :return: True if the referenced object was deleted, otherwise False
    """
    logger.info("## Deleting S3")
    logger.info(bucket_name + object_name)

    # Delete the object
    try:
        s3.delete_object(Bucket=bucket_name, Key=object_name)
    except ClientError as e:
        logger.error(e)
        return False
    return True


def delete_email_item(destination, messageId):
    try:
        table_emails.delete_item(
            Key={"destination": destination, "messageId": messageId}
        )
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])


def delete_address_item(address):
    try:
        table_addresses.delete_item(Key={"address": address})
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])


def find_emails(destination):
    try:
        filtering_exp = Key("destination").eq(destination)
        response = table_emails.query(KeyConditionExpression=filtering_exp)
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])
    else:
        # Clean response
        for I in response["Items"]:
            delete_object(I["bucketName"], I["bucketObjectKey"])
            delete_email_item(destination, I["messageId"])


def cleanup(address):
    find_emails(address)
    delete_address_item(address)


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES ")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)
    try:
        destination = event["pathParameters"]["addressId"]
        user_sub = get_user_sub_from_event(event)
        logger.info("## user_sub deleteing address: %s", user_sub)
        if check_access(table_addresses, user_sub, destination):
            cleanup(destination)
            return create_response(status_code=200, body=None)
    except Exception as e:
        logger.error("## Error deleting address:")
        logger.exception(e)
        return create_response(status_code=500, body=e)
