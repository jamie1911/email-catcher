import io
import json
import os
import logging
import re
from email import policy
from email.parser import BytesParser

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from aws_xray_sdk.core import xray_recorder, patch_all

from util import check_summarize

if os.environ.get("XRAY_ENABLED", "false").lower() == "true":
    XRAY_NAME = os.environ.get("XRAY_NAME", "email-catcher")
    xray_recorder.configure(service=XRAY_NAME)
    patch_all()

LOGGING_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOGGING_LEVEL)

brt = boto3.client(
    service_name="bedrock-runtime",
    config=Config(
        region_name="us-east-1",
    ),
)
s3 = boto3.client("s3")

dynamodb = boto3.resource("dynamodb")
email_table = dynamodb.Table(os.environ["emails_table_name"])
address_table = dynamodb.Table(os.environ["addresses_table_name"])


def summarize(text: str):
    logger.info(f"summarizing text via bedrock-runtime: {text}")
    logger.info(f"Bedrock estimated Tokens Usage: {(len(text)/6)}")
    prompt = f"""
Please provide a summary of the following email content. Do not add any information that is not mentioned in the text below.

<text>
{text}
</text>
"""
    try:
        body = json.dumps(
            {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 4096,
                    "stopSequences": [],
                    "temperature": 0,
                    "topP": 1,
                },
            }
        )

        modelId = "amazon.titan-text-lite-v1"
        accept = "application/json"
        contentType = "application/json"

        response = brt.invoke_model(
            body=body, modelId=modelId, accept=accept, contentType=contentType
        )
        logger.info("## Loading response to json ##")
        response_body = json.loads(response.get("body").read())
        logger.info("## Bedrock client response ##")
        logger.info(response_body["results"][0]["outputText"])
        return response_body["results"][0]["outputText"]
    except Exception as e:
        logger.error("## Bedrock Invoke Model Error ##")
        logger.error(e)
        return None


def set_summary(destination, messageId, summary):
    logger.info(
        f"Setting summary for destination: {destination} and messageId: {messageId}"
    )
    try:
        email_table.update_item(
            Key={"destination": destination, "messageId": messageId},
            UpdateExpression="SET summary_text = :summary",
            ExpressionAttributeValues={":summary": summary},
        )
    except ClientError as e:
        logger.error(
            f"Error setting summary for destination: {destination} and messageId: {messageId}"
        )
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])
    except Exception as e:
        logger.error(
            f"Error setting summary for destination: {destination} and messageId: {messageId}"
        )
        logger.error(e)


def store_email(email, receipt):
    try:
        email_table.put_item(
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

    if check_summarize(address_table, message["mail"]["destination"][0]):
        try:
            data = s3.get_object(
                Bucket=message["receipt"]["action"]["bucketName"],
                Key=message["receipt"]["action"]["objectKey"],
            )
            email_content_bytes = data["Body"].read()
            msg = BytesParser(policy=policy.default).parse(
                io.BytesIO(email_content_bytes)
            )
            email_body = msg.get_body(preferencelist=("plain")).get_content()
            pattern = r"<https?://[^>]*>"
            email_body = re.sub(pattern, "", email_body)
            summary = summarize(email_body)
            set_summary(
                message["mail"]["destination"][0], message["mail"]["messageId"], summary
            )
        except Exception as e:
            logger.error(f"Failed to parse email for AI summary: {e}")
