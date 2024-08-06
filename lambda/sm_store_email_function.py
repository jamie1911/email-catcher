import os
import json
import logging

import boto3

from aws_xray_sdk.core import xray_recorder, patch_all

if os.environ.get("XRAY_ENABLED", "false").lower() == "true":
    XRAY_NAME = os.environ.get("XRAY_NAME", "email-catcher")
    xray_recorder.configure(service=XRAY_NAME)
    patch_all()

LOGGING_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOGGING_LEVEL)

s3 = boto3.client("s3")
ddb_client = boto3.resource("dynamodb")
email_table = ddb_client.Table(os.environ["EMAILS_TABLE_NAME"])


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)

    message = event

    source_bucket = message["receipt"]["action"]["bucketName"]
    source_key = message["receipt"]["action"]["objectKey"]
    destination_key = f"stored_emails/{message['mail']['destination'][0]}/{message['mail']['messageId']}/{message['mail']['messageId']}.eml"

    try:
        # Copy object to new location in S3
        s3.copy_object(
            CopySource={"Bucket": source_bucket, "Key": source_key},
            Bucket=source_bucket,
            Key=destination_key,
        )
        if LOGGING_LEVEL.lower() == "debug":
            s3.copy_object(
                CopySource={"Bucket": source_bucket, "Key": source_key},
                Bucket=source_bucket,
                Key=destination_key + ".orginal",
            )

        # Delete the original object
        s3.delete_object(Bucket=source_bucket, Key=source_key)

        # Record object in DDB
        ddb_email = {
            "destination": message["mail"]["destination"][0],
            "messageId": message["mail"]["messageId"],
            "timestamp": message["mail"]["timestamp"],
            "source": message["mail"]["source"],
            "attachments": [],
            "commonHeaders": message["mail"]["commonHeaders"],
            "bucketName": source_bucket,
            "bucketObjectKey": destination_key,
            "is_read": False,
            "is_processed": False,
        }

        email_table.put_item(Item=ddb_email)
        return ddb_email

    except Exception as e:
        logger.exception("## EXCEPTION ##")
        logger.exception(e)
        raise e
