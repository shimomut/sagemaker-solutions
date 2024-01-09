import time


# FIXME : use poutput() instead of print()
def print_log(logs_client, log_group, stream):

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
