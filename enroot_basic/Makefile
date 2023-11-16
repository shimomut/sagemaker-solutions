
IMAGE_NAME = enroot-test
IMAGE_TAG = latest
SQSH_FILE = ./$(IMAGE_NAME)_$(IMAGE_TAG).sqsh
MOUNT_SRC = ./mount_test
MOUNT_DST = /mount_test

docker-image:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 763104351884.dkr.ecr.us-west-2.amazonaws.com
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

sqsh:
	ENROOT_SQUASH_OPTIONS='-comp gzip -noD' enroot import -o $(SQSH_FILE) dockerd://$(IMAGE_NAME):$(IMAGE_TAG)

docker-run:
	docker run -it $(IMAGE_NAME):$(IMAGE_TAG) /bin/bash

enroot-run:
	enroot start \
		--mount $(MOUNT_SRC):$(MOUNT_DST) \
		--env ENV_TEST1=123 \
		$(SQSH_FILE) \
		/bin/bash

clean:
	if [ -d "${SQSH_FILE}" ]; then \
        rm $(SQSH_FILE); \
    fi
