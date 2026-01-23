#!/usr/bin/env python3
import os
import json
import argparse

from lambda_function import lambda_handler


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Lambda function to send HTML email by SES")
    argparser.add_argument('--sender', action="store", required=True, help='Sender email address')
    argparser.add_argument('--receiver', action="store", required=True, help='Receiver email address')
    argparser.add_argument('--test-event-file', action="store", required=True, help='Test event JSON file')
    args = argparser.parse_args()

    os.environ["SENDER_EMAIL_ADDRESS"] = args.sender
    os.environ["RECEIVER_EMAIL_ADDRESS"] = args.receiver

    with open(args.test_event_file) as fd:
        event = json.load(fd)

    lambda_handler(event, None)
