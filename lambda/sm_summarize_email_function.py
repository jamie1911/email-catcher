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

brk_client = boto3.client("bedrock-runtime", config=Config(region_name="us-east-1"))
s3 = boto3.client("s3")
ddb_client = boto3.resource("dynamodb")
email_table = ddb_client.Table(os.environ["EMAILS_TABLE_NAME"])
address_table = ddb_client.Table(os.environ["ADDRESS_TABLE_NAME"])

TOKEN_LIMIT = 4096
AVG_TOKEN_CHAR_CONVERSION = 3.25
CHARACTER_LIMIT = int(TOKEN_LIMIT * AVG_TOKEN_CHAR_CONVERSION - 1000)


def summarize(text: str):
    prompt = f"""Please provide a summary of the following email content. Do not add any information that is not mentioned in the text.
<text>
{text}
</text>
"""
    logger.debug("## Summarizing text via bedrock-runtime: %s", prompt)
    logger.info(
        "## Bedrock estimated Tokens Usage: %s",
        (len(prompt) / AVG_TOKEN_CHAR_CONVERSION),
    )
    try:
        body = json.dumps(
            {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": TOKEN_LIMIT,
                    "stopSequences": [],
                    "temperature": 0,
                    "topP": 1,
                },
            }
        )

        modelId = "amazon.titan-text-lite-v1"
        accept = "application/json"
        contentType = "application/json"

        response = brk_client.invoke_model(
            body=body, modelId=modelId, accept=accept, contentType=contentType
        )
        logger.debug("## Loading bedrock response to json ##")
        response_body = json.loads(response.get("body").read())
        logger.debug("## Bedrock client response ##")
        logger.debug(response_body["results"][0]["outputText"])
        return response_body["results"][0]["outputText"]
    except Exception as e:
        logger.error("## Bedrock Invoke Model Error ##")
        logger.exception(e)
        return None


def set_summary(destination, messageId, summary):
    logger.info(
        f"## Setting summary for destination: {destination} and messageId: {messageId}"
    )
    try:
        email_table.update_item(
            Key={"destination": destination, "messageId": messageId},
            UpdateExpression="SET summary_text = :summary",
            ExpressionAttributeValues={":summary": summary},
        )
    except ClientError as e:
        logger.error(
            f"## Error setting summary for destination: {destination} and messageId: {messageId}"
        )
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])


def extract_recent_content(email_body: str, char_limit: int) -> str:
    return email_body[:char_limit]


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)

    message = event

    if check_summarize(address_table, message["destination"]):
        data = s3.get_object(
            Bucket=message["bucketName"],
            Key=message["bucketObjectKey"],
        )
        email_content_bytes = data["Body"].read()
        msg = BytesParser(policy=policy.default).parse(io.BytesIO(email_content_bytes))
        try:
            email_body = msg.get_body(preferencelist=("plain", "html")).get_content()
            pattern = r"<https?://[^>]*>"
            email_body = re.sub(pattern, "", email_body)
            email_body = re.sub(r"\n>", "", email_body)
            email_body = re.sub(r">+", "", email_body)
            email_body = re.sub(r"[ \t]+", " ", email_body)
            email_body = extract_recent_content(email_body, CHARACTER_LIMIT)
            summary = summarize(email_body)
            set_summary(message["destination"], message["messageId"], summary)
        except Exception as e:
            logger.error("## Failed to parse email for AI summary:")
            logger.exception(e)

    email_table.update_item(
        Key={"destination": message["destination"], "messageId": message["messageId"]},
        UpdateExpression="SET is_processed = :processed",
        ExpressionAttributeValues={":processed": True},
    )
    return {
        "is_processed": True,
    }
