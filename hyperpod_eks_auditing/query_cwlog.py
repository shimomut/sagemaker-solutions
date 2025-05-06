
import time
import json
import boto3

print_malformed_json = True

region_name = "us-west-2"
log_group_name = "/aws/eks/sagemaker-hyperpod-eks-cluster/cluster"
log_stream_name = "kube-apiserver-audit-a6d77126da55ed7c1bc2c9b923dbb452"

class CwLogsStream:

    def __init__(self, region_name, log_group_name, log_stream_name):
        self.region_name = region_name
        self.log_group_name = log_group_name
        self.log_stream_name = log_stream_name

    def get_events(self, start_time):

        logs_client = boto3.client("logs", region_name=self.region_name)

        next_token = None
        while True:

            params = {
                "logGroupName" : self.log_group_name,
                "logStreamName" : self.log_stream_name,
                "startFromHead" : True,
                "limit" : 1000,
            }

            if next_token:
                params["nextToken"] = next_token
            else:
                params["startTime"] = start_time

            #print("Calling get_log_events:", params)

            try:
                response = logs_client.get_log_events( **params )
            except logs_client.exceptions.ResourceNotFoundException as e:
                print( "Log group or stream not found [ %s, %s ]" % (self.log_group_name, self.log_stream_name) )
                return

            for event in response["events"]:

                if start_time > event["timestamp"]:
                    continue

                self.on_event(event)

            assert "nextForwardToken" in response, "nextForwardToken not found"

            if response["nextForwardToken"] != next_token:
                next_token = response["nextForwardToken"]
            else:
                break

    def on_event(self, event):
        message = event["message"]
        message = message.replace( "\0", "\\0" )
        print( message )


class NodeLabelUpdateEvents(CwLogsStream):

    def __init__(self, region_name, log_group_name, log_stream_name):

        super().__init__(region_name, log_group_name, log_stream_name)
        self.verbs = set()

    def on_event(self, event):
        message = event["message"]
        try:
            d = json.loads(message)
        except json.decoder.JSONDecodeError as e:
            if print_malformed_json:
                #print(e, ":", message)
                pass
            return
        
        try:
            verb = d["verb"]
        except (TypeError, KeyError) as e:
            verb = None

        self.verbs.add(verb)

        # process only update and patch operations
        if verb in {'update', 'patch'}:
            pass
        elif verb in {'watch', 'list', 'create', 'get'}:
            return
        else:
            assert False, f"Unknown verb {verb}"

        try:
            object_name = d["objectRef"]["name"]
        except KeyError:
            object_name = None

        # process only operations against specific node
        if object_name != "hyperpod-i-0fdb3d806306ede29":
            return
        
        labels_updated = False
        if "requestObject" in d:
            if "metadata" in d["requestObject"]:
                if "labels" in d["requestObject"]["metadata"]:
                    labels_updated = True

        if labels_updated:
            print(json.dumps(d, indent=2))
            print("")
            print("---")
            print("")
            
def main():

    node_label_events = NodeLabelUpdateEvents(region_name, log_group_name, log_stream_name)
    
    #start_time = int((time.time() - 24 * 60 * 60) * 1000) # 24 hours
    start_time = int((time.time() - 1 * 60 * 60) * 1000) # 1 hour

    node_label_events.get_events( start_time = start_time )

main()
