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

from util import check_access, create_response, get_user_sub_from_event

if os.environ.get("XRAY_ENABLED", "false").lower() == "true":
    XRAY_NAME = os.environ.get("XRAY_NAME", "email-catcher")
    xray_recorder.configure(service=XRAY_NAME)
    patch_all()

LOGGING_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOGGING_LEVEL)

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
brt = boto3.client(
    service_name="bedrock-runtime",
    config=Config(
        region_name="us-east-1",
    ),
)

addresses_table = dynamodb.Table(os.environ["addresses_table_name"])
emails_table = dynamodb.Table(os.environ["emails_table_name"])


def get_email_file(destination, messageId):
    result = None
    try:
        response = emails_table.get_item(
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


def set_as_read(destination, messageId):
    try:
        emails_table.update_item(
            Key={"destination": destination, "messageId": messageId},
            UpdateExpression="SET isNew = :updated",
            ExpressionAttributeValues={":updated": False},
        )
    except ClientError as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e.response["Error"]["Message"])
        raise e.response["Error"]["Message"]


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
        emails_table.update_item(
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


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)

    try:
        destination = event["pathParameters"]["addressId"]
        messageId = event["pathParameters"]["messageId"]
        user_sub = get_user_sub_from_event(event)

        has_access, full_response = check_access(
            addresses_table, user_sub, destination, full_response=True
        )
        logger.info(f"has_access: {has_access}")
        logger.info(f"full_response: {full_response}")
        if has_access:
            email_file = get_email_file(destination, messageId)
            if email_file is not None:
                data = s3.get_object(
                    Bucket=email_file["bucketName"], Key=email_file["bucketObjectKey"]
                )
                email_content_bytes = data["Body"].read()
                contents = email_content_bytes.decode("utf-8")
                summary = email_file.get("summary_text", None)

                if email_file["isNew"] == True:
                    set_as_read(destination, messageId)
                    try:
                        summarize_email_check = full_response.get("summarize_emails")
                        logger.info(f"summarize_email: {summarize_email_check}")
                        if summarize_email_check:
                            msg = BytesParser(policy=policy.default).parse(io.BytesIO(email_content_bytes))
                            email_body = msg.get_body(preferencelist=('plain')).get_content()
                            pattern = r"<https?://[^>]*>"
                            email_body = re.sub(pattern, "", email_body)
                            summary = summarize(email_body)
                            set_summary(destination, messageId, summary)
                    except Exception as e:
                        logger.error("Failed to parse email for AI summary: ", e)

                email_response = {"body": contents, "summary": summary}
                return create_response(
                    status_code=200,
                    body=email_response,
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
        return create_response(
            status_code=500,
            body=e,
        )
