
put-rule:
	aws events put-rule --name MySageMakerRule --event-pattern file://event-pattern.json

list-rules:
	aws events list-rules

describe-rule:
	aws events describe-rule --name MySageMakerRule


create-topic:
	aws sns create-topic --name MySageMakerNotificationTopic

subscribe:
	aws sns subscribe \
		--topic-arn arn:aws:sns:us-west-2:842413447717:MySageMakerNotificationTopic \
		--protocol email \
		--notification-endpoint xyz123@amazon.com

# You will receive an email "AWS Notification - Subscription Confirmation" and need to confirm.

put-target:
	aws events put-targets --rule MySageMakerRule --targets "Id"="1","Arn"="arn:aws:sns:us-west-2:842413447717:MySageMakerNotificationTopic"

# You can update the cluster status (e.g. scale up), and confirm you receive emails.