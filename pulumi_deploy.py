#!python
import os
import subprocess
import argparse
import re
import yaml
import json
from typing import List

import pulumi
import boto3

PULUMI_ORG = "PULUMI_ORG"
PULUMI_PROJECT_NAME = "PULUMI_PROJECT_NAME"
PULUMI_PROJECT_DESC = "pulumi code to support and deploy the email catcher"
PULUMI_WORK_DIR = os.path.join(os.path.dirname(__file__), ".")

pulumi_yaml_settings = {
    "name": PULUMI_PROJECT_NAME,
    "runtime.name": "python",
    "runtime.options.virtualenv": "venv",
    "description": PULUMI_PROJECT_DESC,
}


def pulumi_yaml(file_path, updates):
    def set_nested_value(yaml_dict, key_path, value):
        keys = key_path.split(".")
        for key in keys[:-1]:
            if key not in yaml_dict or not isinstance(yaml_dict[key], dict):
                yaml_dict[key] = {}
            yaml_dict = yaml_dict[key]
        yaml_dict[keys[-1]] = value

    # Read the existing YAML file or start with an empty dictionary if it does not exist
    try:
        with open(file_path, "r") as file:
            yaml_content = yaml.safe_load(file) or {}
    except FileNotFoundError:
        yaml_content = {}

    # Update YAML content with provided updates
    for key_path, value in updates.items():
        set_nested_value(yaml_content, key_path, value)

    # Write the updated content back to the file, creating it if it doesn't exist
    with open(file_path, "w") as file:
        yaml.safe_dump(yaml_content, file, default_flow_style=False)


pulumi_yaml(f"{PULUMI_WORK_DIR}/Pulumi.yaml", pulumi_yaml_settings)


def frontend_env_config(pulumi_outputs):
    """Updates frontend config file on frontend deployment."""
    with open(f"{PULUMI_WORK_DIR}/frontend/src/aws-exports.js", "r") as file:
        content = file.read()

    replacements = {
        "region": pulumi_outputs["cognito_region"].value,
        "userPoolId": pulumi_outputs["cognito_user_pool_id"].value,
        "userPoolWebClientId": pulumi_outputs["cognito_user_pool_client"].value,
        "apiGatewayurl": f"{pulumi_outputs['api_gateway_url'].value}/",
        "emailDomain": pulumi_outputs["ses_email_domain"].value,
    }

    for key, value in replacements.items():
        # Pattern to match the key and its value
        pattern = rf'({key}: )"[^"]*"'
        # Replacement string with the new value
        replacement = rf'\1"{value}"'
        # Substitute the old value with the new value
        content = re.sub(pattern, replacement, content)

    # Write the updated content back to the file
    with open(f"{PULUMI_WORK_DIR}/frontend/src/aws-exports.js", "w") as file:
        file.write(content)


def build_frontend():
    try:
        print("building frontend...")
        subprocess.run(
            ["rm", "-rf", "./build"],
            check=True,
            cwd=f"{PULUMI_WORK_DIR}/frontend",
            capture_output=True,
        )
        subprocess.run(
            ["apt-get", "install", "-y", "nodejs", "npm"],
            check=True,
            cwd=f"{PULUMI_WORK_DIR}",
            capture_output=True,
        )
        subprocess.run(
            ["npm", "install"],
            check=True,
            cwd=f"{PULUMI_WORK_DIR}/frontend",
            capture_output=True,
        )
        subprocess.run(
            ["npm", "run", "build"],
            check=True,
            cwd=f"{PULUMI_WORK_DIR}/frontend",
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print("Error:", e.stderr)
        return False


def upload_frontend_to_s3(bucket_name: str, cloudfront_id: str):
    try:
        print("uploading frontend to s3...")
        subprocess.run(
            ["aws", "s3", "sync", ".", f"s3://{bucket_name}", "--delete"],
            check=True,
            cwd=f"{PULUMI_WORK_DIR}/frontend/build",
            capture_output=True,
        )
        print("invalidating cloudfront cache...")
        subprocess.run(
            [
                "aws",
                "cloudfront",
                "create-invalidation",
                "--distribution-id",
                cloudfront_id,
                "--paths",
                "/*",
            ],
            check=True,
            cwd=f"{PULUMI_WORK_DIR}/frontend/build",
            capture_output=True,
        )
        return True
    except Exception as e:
        print("Error:")
        print(e)
        return False


def set_s3_bucket_deny_policy(buckets: List[str]):
    s3 = boto3.client("s3")
    if buckets:
        for bucket in buckets:
            print(f"Setting deny bucket policy on: {bucket}")
            try:
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "DenyPutObject",
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:PutObject*",
                            "Resource": f"arn:aws:s3:::{bucket}/*",
                        }
                    ],
                }
                s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
            except Exception as e:
                print(f"Couldn't set deny bucket policy on: {bucket}: {e}")


def main(stack_name: str, command: str, region: str, force: bool):
    stack_name_fqdn = pulumi.automation.fully_qualified_stack_name(
        PULUMI_ORG, PULUMI_PROJECT_NAME, stack_name
    )

    print("preparing environment...")
    subprocess.run(
        ["pip", "install", "-r", "requirements.txt"],
        check=True,
        cwd=PULUMI_WORK_DIR,
        capture_output=True,
    )
    subprocess.run(
        ["mkdir", "-p", "./code_layer"],
        check=True,
        cwd=f"{PULUMI_WORK_DIR}",
        capture_output=True,
    )
    subprocess.run(
        [
            "pip",
            "install",
            "--upgrade",
            "-r",
            "./lambda/requirements.txt",
            "-t",
            "./code_layer/python",
        ],
        check=True,
        cwd=f"{PULUMI_WORK_DIR}",
        capture_output=True,
    )

    # check if our stack exists already
    stack_exists = None
    try:
        pulumi.automation.select_stack(stack_name=stack_name_fqdn, work_dir=PULUMI_WORK_DIR)
        print("Found existing stack...")
        stack_exists = True
    except pulumi.automation.errors.StackNotFoundError:
        stack_exists = False
        print("First time stack is deploying...")


    # Create our stack using a local program in the work_dir
    print("initializing stack...")
    stack = pulumi.automation.create_or_select_stack(
        stack_name=stack_name_fqdn, work_dir=PULUMI_WORK_DIR
    )

    print("setting up stack config...")
    stack.set_config("aws:region", pulumi.automation.ConfigValue(value=region))
    stack.set_config(
        "aws:skipCredentialsValidation", pulumi.automation.ConfigValue(value="true")
    )
    stack.set_config(
        "aws:skipMetadataApiCheck", pulumi.automation.ConfigValue(value="false")
    )

    if command == "preview":
        print("stack previewing...")
        stack.preview(on_output=print, color="always")
        if not stack_exists or os.environ.get("CHANGES_IN_FRONTEND", "False") == "True":
            build_frontend()
        print("stack preview complete")

    if command == "refresh":
        print("stack refreshing...")
        stack.refresh(on_output=print, color="always")
        print("stack refresh complete")

    if command == "destroy":
        if force is False:
            if input("are you sure? (y/n)") != "y":
                exit()
        print("stack destroying...")
        buckets_needing_deny = []
        buckets_needing_deny.append(stack.outputs().get("portal_bucket_name").value if stack.outputs().get("portal_bucket_name") else None)
        buckets_needing_deny.append(stack.outputs().get("emails_bucket_name").value if stack.outputs().get("emails_bucket_name") else None)
        set_s3_bucket_deny_policy(buckets_needing_deny)
        stack.destroy(on_output=print, color="always")
        print("stack destroy complete")
        stack.workspace.remove_stack(stack_name_fqdn)
        print("stack remove complete")

    if command == "up":
        print("stack deploying...")
        pulumi_up = stack.up(on_output=print, color="always")
        print("stack deploy complete")
        print(f"project name: {PULUMI_PROJECT_NAME}")
        print(f"stack name: {stack_name}")
        if not stack_exists or os.environ.get("CHANGES_IN_FRONTEND", "False") == "True":
            frontend_env_config(pulumi_up.outputs)
            build_frontend()
            upload_frontend_to_s3(
                bucket_name=pulumi_up.outputs["portal_bucket_name"].value,
                cloudfront_id=pulumi_up.outputs["cf_distribution_id"].value,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Pulumi automation for {PULUMI_PROJECT_NAME}"
    )
    parser.add_argument(
        "--stack-name", type=str, help="pulumi stack name to run against", required=True
    )
    parser.add_argument(
        "--command",
        type=str,
        help="command to run against stack: up, refresh, preview, destroy",
        default="preview",
    )
    parser.add_argument(
        "--region", type=str, help="AWS region to run in", default="us-east-2"
    )
    parser.add_argument("--force", action="store_true", help="Force without prompts")
    args = parser.parse_args()

    main(
        stack_name=args.stack_name,
        command=args.command,
        region=args.region,
        force=args.force,
    )