local-test1:
	python3 lambda_function.py \
	--sender shimomut+sender@amazon.com \
	--receiver shimomut+receiver@amazon.com \
	--test-event-file test_events/cluster_status_change.json

local-test2:
	python3 lambda_function.py \
	--sender shimomut+sender@amazon.com \
	--receiver shimomut+receiver@amazon.com \
	--test-event-file test_events/node_health_event.json

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