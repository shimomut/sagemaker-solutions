
put-rule:
	aws events put-rule --name MySageMakerRule --event-pattern file://event-pattern.json

list-rules:
	aws events list-rules

describe-rule:
	aws events describe-rule --name MySageMakerRule

delete-rule:
	aws events delete-rule --name MySageMakerRule

create-topic:
	aws sns create-topic --name MySageMakerNotificationTopic

subscribe:
	aws sns subscribe \
		--topic-arn arn:aws:sns:us-west-2:842413447717:MySageMakerNotificationTopic \
		--protocol email \
		--notification-endpoint shimomut@amazon.com

# You will receive an email "AWS Notification - Subscription Confirmation" and need to confirm.

# Here, using manually created IAM Role for the target.

put-target:
	aws events put-targets --rule MySageMakerRule \
		--targets "Id"="1","Arn"="arn:aws:sns:us-west-2:842413447717:MySageMakerNotificationTopic","RoleArn"="arn:aws:iam::842413447717:role/service-role/Amazon_EventBridge_Invoke_Sns_747096842"

remove-target:
	aws events remove-targets --rule MySageMakerRule \
		--ids 1


# You can update the cluster status (e.g. scale up), and confirm you receive emails.

# For HyperPod EKS, you can set node label to trigger instance replacement, and receive emails.
# e.g., kubectl label node hyperpod-i-0fdc8ceb3bfecc215 sagemaker.amazonaws.com/node-health-status=UnschedulablePendingReplacement --overwrite=true

# For HyperPod Slurm, as of 2025-05-09, only EC2 level instance degradation events are supported.

deploy:
	aws cloudformation create-stack \
	--stack-name hyperpod-events-stack \
	--template-body file://hyperpod_events.yaml \
	--parameters \
		ParameterKey=SenderEmailAddress,ParameterValue=shimomut+sender@amazon.com \
		ParameterKey=ReceiverEmailAddress,ParameterValue=shimomut+receiver@amazon.com \
	--capabilities CAPABILITY_IAM

delete:
	aws cloudformation delete-stack \
	--stack-name hyperpod-events-stack