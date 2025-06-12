
create-pod-role:
	aws cloudformation create-stack \
	--stack-name pod-identity-test-role \
	--template-body file://./pod-role.yaml \
    --capabilities CAPABILITY_IAM

create-service-account:
	kubectl apply -f service-account.yaml

deploy-app:
	kubectl apply -f deployment.yaml

list-pods:
	kubectl get pods -n pod-identity-test

POD_NAME := POD_NAME

exec-bash-in-pod:
	kubectl exec -it ${POD_NAME} -n pod-identity-test -- bash

delete-app:
	kubectl delete -f deployment.yaml

delete-service-account:
	kubectl delete -f service-account.yaml