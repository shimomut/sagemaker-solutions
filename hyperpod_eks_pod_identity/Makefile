
create-pod-role:
	aws cloudformation create-stack \
	--stack-name pod-identity-test-role \
	--template-body file://./pod-role.yaml \
    --capabilities CAPABILITY_IAM


create-service-account:
	kube
	kubectl apply -f service-account.yaml

deploy:
	kubectl apply -f deployment.yaml

delete:
	kubectl delete -f deployment.yaml

