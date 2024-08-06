import os
import io
import logging
from email import policy
from email.parser import BytesParser
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


def add_ddb_attachments(destination, messageId, attachments):
    email_table.update_item(
        Key={"destination": destination, "messageId": messageId},
        UpdateExpression="SET attachments = :updated",
        ExpressionAttributeValues={":updated": attachments},
    )


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)

    message = event
    attachments = []
    email_object = s3.get_object(
        Bucket=message["bucketName"],
        Key=message["bucketObjectKey"],
    )

    email_content_bytes = email_object["Body"].read()
    email_content = BytesParser(policy=policy.default).parse(
        io.BytesIO(email_content_bytes)
    )

    # Process and upload attachments
    attachments = []
    for part in email_content.walk():
        content_disposition = part.get("Content-Disposition", "")
        if "attachment" in content_disposition or "inline" in content_disposition:
            filename = part.get_filename()
            if not filename:
                # Generate a filename if not present
                filename = "inline_attachment"
            # Save the attachment to S3
            s3.put_object(
                Bucket=message["bucketName"],
                Key=f"stored_emails/{message['destination']}/{message['messageId']}/attachments/{filename}",
                Body=part.get_payload(decode=True),
            )
            # Record metadata
            metadata = {
                "filename": filename,
                "Content-Type": part.get_content_type(),
                "Content-Transfer-Encoding": part["Content-Transfer-Encoding"],
                "Content-ID": part["Content-ID"],
                "X-Attachment-Id": part["X-Attachment-Id"],
            }
            attachments.append(metadata)
            # Optionally, remove attachment from the email to reduce size
            part.set_payload(None)

    # # Save the new email without attachments
    s3.put_object(
        Bucket=message["bucketName"],
        Key=message["bucketObjectKey"],
        Body=email_content.as_bytes(),
    )
    add_ddb_attachments(message["destination"], message["messageId"], attachments)
    message["attachments"] = attachments
    logger.info(
        f"Email saved without attachments: {message['bucketName']}/{message['bucketObjectKey']}"
    )
    return message
