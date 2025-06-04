#### Preparation

1. Create an IAM Role ("ImdbProxyTestRole")

    - Trust entities should include following:

        ```
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "sagemaker.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                },
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": "arn:aws:iam::842413447717:role/MySageMakerClusterInstanceRole"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        ```

1. Edit instance group role

    - Add following permission:

        ```
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Resource": "arn:aws:iam::842413447717:role/ImdbProxyTestRole"
                }
            ]
        }
        ```


#### Test before installation

1. Remove original iptables entry to SageMakerRoleProxyAgent

    ```
    make remove-original-iptables-entry
    ```

1. Add IMDB proxy in iptables

    ```
    make add-proxy-iptables-entries
    ```

1. Run IMDB proxy for testing

    ```
    run-proxy
    ```

1. Verify if you get expected Roles

    ```
    $ aws sts get-caller-identity
    {
        "UserId": "AROA4II6BDIS2CKJADTCY:test-session",
        "Account": "842413447717",
        "Arn": "arn:aws:sts::842413447717:assumed-role/ImdbProxyTestRole/test-session"
    }

    $ sudo aws sts get-caller-identity
    {
        "UserId": "AROA4II6BDIS7GQY4LYID:SageMaker",
        "Account": "842413447717",
        "Arn": "arn:aws:sts::842413447717:assumed-role/MySageMakerClusterInstanceRole/SageMaker"
    }
    ```

1. Verify that you have (or don't have) expected permissions

    ```
    $ aws s3 ls

    An error occurred (AccessDenied) when calling the ListBuckets operation: User: arn:aws:sts::842413447717:assumed-role/ImdbProxyTestRole/test-session is not authorized to perform: s3:ListAllMyBuckets because no identity-based policy allows the s3:ListAllMyBuckets action    
    ```


#### Install this solution as a service

(WIP)

1. Install the solution as a systemd service

    ```
    make install-as-systemd-service
    ```

1. Enable and start the service

    ```
    make enable-and-start-service
    ```

1. Verify by rebooting the instance

    ```
    sudo reboot
    ```