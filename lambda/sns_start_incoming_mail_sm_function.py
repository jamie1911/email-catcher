import json
import os
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

stepfunction_client = boto3.client("stepfunctions")

incoming_mail_state_machine_arn = os.environ["INCOMING_MAIL_STATE_MACHINE_ARN"]


def lambda_handler(event, context):
    logger.info("## ENVIRONMENT VARIABLES")
    logger.info(os.environ)
    logger.info("## EVENT")
    logger.info(event)

    stepfunction_client.start_execution(
        stateMachineArn=incoming_mail_state_machine_arn,
        input=event["Records"][0]["Sns"]["Message"],
    )
