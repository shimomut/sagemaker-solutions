run:
	docker run myhello

build:
	docker build --tag myhello .

login:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-west-2.amazonaws.com

tag:
	docker tag myhello:latest 842413447717.dkr.ecr.us-west-2.amazonaws.com/myhello:latest

push:
	docker push 842413447717.dkr.ecr.us-west-2.amazonaws.com/myhello:latest