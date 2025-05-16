import os
import json

import boto3


def get_console_url(event):
    region = event["region"]
    cluster_name = event["detail"]["ClusterName"]
    console_url = f"https://{region}.console.aws.amazon.com/sagemaker/home?region={region}#/cluster-management/{cluster_name}"
    return console_url


def format_html_for_cluster_status_event(event):

    html_body = '<body style="font-family:Helvetica; font-size: 11pt;">\n'

    # Table of summary
    html_body += '<table>\n'
    
    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "AWS account:", 
        event["account"]
    )
    
    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Region:", 
        event["region"]
    )
    
    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Cluster name:", 
        event["detail"]["ClusterName"]
    )

    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Cluster status:", 
        event["detail"]["ClusterStatus"]
    )

    html_body += '</table>\n'

    html_body += "<br>\n"

    # Table of instance groups
    html_body += '<table border="1" >\n'
    html_body += '<caption>Instance groups</caption>\n'

    # Header row
    html_body += '<tr bgcolor="#ccccff"> <td>%s</td> <td>%s</td> <td>%s</td> <td>%s</td> </tr>\n' % (
        "Name", "Status", "Current count", "Target count"
    )

    # Data row
    for instance_group in event["detail"]["InstanceGroups"]:
        html_body += "<tr> <td>%s</td> <td>%s</td> <td>%s</td> <td>%s</td> </tr>\n" % (
            instance_group["InstanceGroupName"],
            instance_group["Status"],
            instance_group["CurrentCount"],
            instance_group["TargetCount"],
        )

    html_body += '</table>\n'

    html_body += "<br>\n"

    # Hyperlink to console page
    html_body += '<a href="%s">Link to HyperPod console</a>\n' % get_console_url(event)

    html_body += "</body>"

    return html_body


def format_html_for_node_health_event(event):

    html_body = '<body style="font-family:Helvetica; font-size: 11pt;">\n'

    # Table of summary
    html_body += '<table>\n'
    
    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "AWS account:", 
        event["account"]
    )
    
    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Region:", 
        event["region"]
    )
    
    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Cluster name:", 
        event["detail"]["ClusterName"]
    )

    html_body += '</table>\n'

    html_body += "<br>\n"

    # Table of instance groups
    html_body += '<table border="1" >\n'
    html_body += '<caption>Instance health info</caption>\n'

    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Instance ID", 
        event["detail"]["InstanceId"]
    )

    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Health Status", 
        event["detail"]["HealthSummary"]["HealthStatus"]
    )

    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Health Status Reason", 
        event["detail"]["HealthSummary"]["HealthStatusReason"]
    )

    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "RepairAction", 
        event["detail"]["HealthSummary"]["RepairAction"]
    )

    html_body += "<tr> <td>%s</td> <td>%s</td> </tr>\n" % (
        "Recommendation", 
        event["detail"]["HealthSummary"]["Recommendation"]
    )

    html_body += '</table>\n'

    html_body += "<br>\n"

    # Hyperlink to console page
    html_body += '<a href="%s">Link to HyperPod console</a>\n' % get_console_url(event)

    html_body += "</body>"

    return html_body



def lambda_handler(event, context):
    ses = boto3.client('ses')
    
    email_source = os.environ['SENDER_EMAIL_ADDRESS']
    email_recipient = os.environ['RECEIVER_EMAIL_ADDRESS']

    event_type = event["detail-type"]
    if event_type == "SageMaker HyperPod Cluster State Change":
        cluster_status = event["detail"]["ClusterStatus"]
        email_subject = f"HyperPod Cluster State Change - {cluster_status}"
        email_body = format_html_for_cluster_status_event(event)
    elif event_type == "SageMaker HyperPod Cluster Node Health Event":
        node_status = event["detail"]["HealthSummary"]["HealthStatus"]
        email_subject = f"HyperPod Cluster Node Health Event - {node_status}"
        email_body = format_html_for_node_health_event(event)
    else:
        assert False, f"Unknown event type {event_type}"

    ses.send_email(
        Source=email_source,
        Destination={
            'ToAddresses': [email_recipient]
        },
        Message={
            'Subject': {
                "Charset": "UTF-8",
                'Data': email_subject,
            },
            'Body': {
                "Html": {
                    "Charset": "UTF-8",
                    "Data": email_body,
                }
            }
        }
    )

    return {
        'statusCode': 200,
        'body': json.dumps('Email sent successfully.')
    }


if __name__ == "__main__":

    import argparse

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
