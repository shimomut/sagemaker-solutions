local-test1:
	python3 local_test.py \
	--sender shimomut+sender@amazon.com \
	--receiver shimomut+receiver@amazon.com \
	--test-event-file test_events/cluster_status_change.json

local-test2:
	python3 local_test.py \
	--sender shimomut+sender@amazon.com \
	--receiver shimomut+receiver@amazon.com \
	--test-event-file test_events/node_health_event.json

dump-events:
	@if [ -z "$(CLUSTER_NAME)" ]; then \
		echo "Error: CLUSTER_NAME is required"; \
		echo "Usage: make dump-events CLUSTER_NAME=my-cluster [REGION=us-west-2] [OUTPUT=events.json]"; \
		exit 1; \
	fi
	python3 dump_cluster_events.py \
		--cluster-name $(CLUSTER_NAME) \
		--region $(or $(REGION),us-west-2) \
		$(if $(OUTPUT),--output $(OUTPUT),) \
		--pretty

local-test3:
	python3 local_test.py \
	--sender shimomut+sender@amazon.com \
	--receiver shimomut+receiver@amazon.com \
	--test-event-file test_events/cluster_event.json

embed:
	@echo "Embedding Lambda function into CloudFormation template..."
	@awk '/# LAMBDA_CODE_PLACEHOLDER/ { \
		while ((getline line < "lambda_function.py") > 0) { \
			if (line == "") { \
				print ""; \
			} else { \
				print "          " line; \
			} \
		} \
		close("lambda_function.py"); \
		next; \
	} \
	{ print }' hyperpod-event-bridge-email-template.yaml > hyperpod-event-bridge-email.yaml
	@echo "Created hyperpod-event-bridge-email.yaml with embedded Lambda code"

deploy: embed
	aws cloudformation create-stack \
	--stack-name hyperpod-events-stack \
	--template-body file://hyperpod-event-bridge-email.yaml \
	--parameters \
		ParameterKey=SenderEmailAddress,ParameterValue=shimomut+sender@amazon.com \
		ParameterKey=ReceiverEmailAddress,ParameterValue=shimomut+receiver@amazon.com \
	--capabilities CAPABILITY_IAM

delete:
	aws cloudformation delete-stack \
	--stack-name hyperpod-events-stack

clean:
	rm -f hyperpod-event-bridge-email.yaml