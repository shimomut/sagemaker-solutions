
import sys
import json
import fnmatch
import re
import datetime

import boto3

region_name = "us-west-2"
eks_cluster_name = "sagemaker-hyperpod-eks-cluster"
log_group_name = f"/aws/eks/{eks_cluster_name}/cluster"
start_datetime = "2025-05-06T18:00:00Z" # in UTC
end_datetime = "2025-05-06T23:10:00Z" # in UTC
object_name = "hyperpod-i-0fdb3d806306ede29"


def datetime_to_timestamp_ms(dt):
    if dt:
        return int(datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ").timestamp() * 1000)
    else:
        return None


class CwLogsGroup:

    def __init__(self, region_name, log_group_name):
        self.region_name = region_name
        self.log_group_name = log_group_name

    def list_streams_all(self, pattern="*", start_datetime=None, end_datetime=None):

        start_timestamp = datetime_to_timestamp_ms(start_datetime)
        end_timestamp = datetime_to_timestamp_ms(end_datetime)

        logs_client = boto3.client("logs", region_name=self.region_name)

        streams = []
        next_token = None
        while True:

            params = {
                "logGroupName" : self.log_group_name,
                "limit" : 5,
            }

            if next_token:
                params["nextToken"] = next_token

            try:
                response = logs_client.describe_log_streams(**params)
            except logs_client.exceptions.ResourceNotFoundException as e:
                print( f"Log group [{self.log_group_name}] not found" )
                sys.exit(1)
            
            for stream in response["logStreams"]:
                if not fnmatch.fnmatch(stream["logStreamName"], pattern):
                    continue

                if end_timestamp and stream["firstEventTimestamp"] > end_timestamp:
                    continue

                if start_timestamp and stream["lastEventTimestamp"] < start_timestamp:
                    continue

                streams.append(stream)

            if "nextToken" in response and response["nextToken"]:
                next_token = response["nextToken"]
                continue
            
            break

        return streams        


class CwLogsStream:

    def __init__(self, region_name, log_group_name, log_stream_name):
        self.region_name = region_name
        self.log_group_name = log_group_name
        self.log_stream_name = log_stream_name

    def iter_events_all(self, start_datetime=None, end_datetime=None):

        start_timestamp = datetime_to_timestamp_ms(start_datetime)
        end_timestamp = datetime_to_timestamp_ms(end_datetime)

        logs_client = boto3.client("logs", region_name=self.region_name)

        next_token = None
        while True:

            params = {
                "logGroupName" : self.log_group_name,
                "logStreamName" : self.log_stream_name,
                "startFromHead" : True,
                #"limit" : 100,
            }

            if start_timestamp:
                params["startTime"] = start_timestamp

            if end_timestamp:
                params["endTime"] = end_timestamp

            if next_token:
                params["nextToken"] = next_token
                del params["startTime"]

            # print("Calling get_log_events:", params)

            try:
                response = logs_client.get_log_events( **params )
            except logs_client.exceptions.ResourceNotFoundException as e:
                print( "Log group or stream not found [ %s, %s ]" % (self.log_group_name, self.log_stream_name) )
                sys.exit(1)

            # print("Num events:", len(response["events"]))

            # if len(response["events"]):
            #     print("Timestamp:", response["events"][0]["timestamp"])

            for event in response["events"]:
                yield event

            assert "nextForwardToken" in response, "nextForwardToken not found"

            if response["nextForwardToken"] != next_token:
                next_token = response["nextForwardToken"]
            else:
                break

            print(".", end="", flush=True)


def print_audit_event(audit_event):

    print("")
    print(json.dumps(audit_event, indent=2))
    print("")
    print("---")


def main():

    log_group = CwLogsGroup(region_name, log_group_name)
    
    streams = log_group.list_streams_all(
        pattern = "kube-apiserver-audit-*",
        start_datetime = start_datetime,
        end_datetime = end_datetime,
        )
    
    detected_audit_events = []

    for stream in streams:

        log_stream_name = stream["logStreamName"]

        print("")
        print( f"Processing log stream {log_stream_name}")
        print("")

        log_stream = CwLogsStream(region_name, log_group_name, log_stream_name)

        for log_event in log_stream.iter_events_all(
                start_datetime = start_datetime,
                end_datetime = end_datetime,
            ):

            timestamp = log_event["timestamp"]
            message = log_event["message"]

            # Use regex to check object name before parsing entire message as a JSON string,
            # because long messages are truncated at 256KB. 
            re_result = re.search(r'"objectRef":(\{[^}]+\})', message)
            if re_result:
                object_ref = json.loads(re_result.group(1))
                if "name" not in object_ref or object_ref["name"] != object_name:
                    continue
            else:
                continue

            try:
                audit_event = json.loads(message)
            except json.decoder.JSONDecodeError as e:
                print(e, ":", message)
                continue
            
            # Skip unexpected data
            if not isinstance(audit_event, dict) or "kind" not in audit_event or audit_event["kind"] != "Event":
                continue

            try:
                verb = audit_event["verb"]
            except (TypeError, KeyError) as e:
                verb = None

            # process only update and patch operations
            if verb in {'update', 'patch'}:
                pass
            elif verb in {'watch', 'list', 'create', 'delete', 'get', 'post'}:
                continue
            else:
                print_audit_event(audit_event)
                assert False, f"Unknown verb {verb}"

            labels_updated = False
            if "requestObject" in audit_event:
                if "metadata" in audit_event["requestObject"]:
                    if "labels" in audit_event["requestObject"]["metadata"]:
                        labels_updated = True

            if labels_updated:
                detected_audit_events.append( (timestamp, audit_event) )

    print("")
    print( f"Printing detected audit events in chronological order.")
    print("")

    t = 0
    for timestamp, audit_event in sorted(detected_audit_events, key=lambda x: x[0]):
        assert t<=timestamp
        t = timestamp
        print_audit_event(audit_event)

    print("")
    print( f"Done.")
    print("")

main()
