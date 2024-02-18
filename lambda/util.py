import json
import os
import logging
from typing import Dict, Any, Union

from aws_xray_sdk.core import xray_recorder, patch_all

if os.environ.get("XRAY_ENABLED", "false").lower() == "true":
    XRAY_NAME = os.environ.get("XRAY_NAME", "email-catcher")
    xray_recorder.configure(service=XRAY_NAME)
    patch_all()

LOGGING_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOGGING_LEVEL)


def create_response(
    status_code: int,
    body: Union[str, Dict[str, Any]],
    additional_headers: Dict[str, Any] = {},
    jsonify_body: bool = True,
):
    headers = {
        "access-control-allow-headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "access-control-allow-methods": "DELETE,GET,HEAD,OPTIONS,PATCH,POST,PUT",
        "access-control-allow-origin": "*",
    }

    additional_headers.update(headers)

    return {
        "statusCode": status_code,
        "body": json.dumps(body) if jsonify_body is True else body,
        "headers": additional_headers,
    }


def check_access(addresses_table, user_sub, destination, full_response=False):
    try:
        response = addresses_table.get_item(Key={"address": destination})
        item = response.get("Item", None)

        if item and item.get("user_sub") == user_sub:
            logger.info("## ACCESS EXISTS, CONTINUE")
            return (True, item) if full_response else True
        else:
            logger.info("## ACCESS DOESN'T EXIST")
            return (False, item) if full_response else False
    except Exception as e:
        logger.error("## DynamoDB Client Exception")
        logger.error(e)
        raise e


def get_user_sub_from_event(event):
    return event["requestContext"]["authorizer"]["claims"]["sub"]
