import time
import fnmatch

import boto3


def _list_log_groups_all( logs_client, prefix ):

    log_groups = []
    next_tolen = None

    while True:

        params = {
            "limit" : 50,
        }

        if prefix:
            params["logGroupNamePrefix"] = prefix

        if next_tolen:
            params["nextToken"] = next_tolen

        response = logs_client.describe_log_groups(**params)

        log_groups += response["logGroups"]

        if "nextToken" in response:
            next_tolen = response["nextToken"]
        else:
            break
    
    return log_groups


def list_log_groups(args):

    logs_client = boto3.client("logs")

    prefix = args.pattern
    pos = prefix.find("*")
    if pos>=0:
        prefix = prefix[:pos]
    pos = prefix.find("?")
    if pos>=0:
        prefix = prefix[:pos]

    last_found_log_group = None
    num_found = 0

    print("Log groups:")
    for log_group in _list_log_groups_all( logs_client, prefix ):
        if fnmatch.fnmatch( log_group["logGroupName"], args.pattern ):
            print( "  " + log_group["logGroupName"] )
            last_found_log_group = log_group
            num_found += 1

    if num_found==1:
        print("")
        print("Streams:")
        response = logs_client.describe_log_streams( logGroupName = last_found_log_group["logGroupName"] )
        for stream in response["logStreams"]:
            print( "  " + stream["logStreamName"] )
            

def print_log(log_group, stream):

    logs_client = boto3.client("logs")

    # FIXME : should use cluster creation time
    start_time = int( ( time.time() - 24 * 60 * 60 ) * 1000 )

    next_token = None
    while True:

        params = {
            "logGroupName" : log_group,
            "logStreamName" : stream,
            "startFromHead" : True,
            "limit" : 1000,
        }

        if next_token:
            params["nextToken"] = next_token
        else:
            params["startTime"] = start_time

        try:
            response = logs_client.get_log_events( **params )
        except logs_client.exceptions.ResourceNotFoundException as e:
            print( "Log group or stream not found [ %s, %s ]" % (args.log_group, args.stream) )
            return

        for event in response["events"]:

            if start_time > event["timestamp"]:
                continue

            message = event["message"]
            message = message.replace( "\0", "\\0" )
            print( message )

        assert "nextForwardToken" in response, "nextForwardToken not found"

        if response["nextForwardToken"] != next_token:
            next_token = response["nextForwardToken"]
        else:
            break
