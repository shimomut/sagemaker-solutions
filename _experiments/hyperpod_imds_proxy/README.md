### How to use downgraded (less permissive) IAM role for non-root users

#### Overview

There are cases when you want to use downgraded (less permissive) IAM role for non-root users to restrict access to some AWS cloud side resources.

- Write access to S3.
- Read access to Secrets Manager secret.
- Invoke Lambda function

This solution explains how to achieve this by running a local proxy server for [IMDS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html) and use downgraded IAM role for non-root users.


#### Preparation

1. Create an IAM Role ("ImdsProxyTestRole")

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

    - Add minimum required permissions including what [this document](https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-prerequisites-iam.html#sagemaker-hyperpod-prerequisites-iam-role-for-hyperpod) explains.

1. Edit instance group role

    - Add following permission:

        ```
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Resource": "arn:aws:iam::842413447717:role/ImdsProxyTestRole"
                }
            ]
        }
        ```


#### Test before installation

1. Remove original iptables entry to SageMakerRoleProxyAgent

    ```
    make remove-original-iptables-entry
    ```

1. Add IMDS proxy in iptables

    ```
    make add-proxy-iptables-entries
    ```

1. Block direct access to SageMakerRoleProxyAgent

    ```
    make block-direct-access-to-sagemaker-role
    ```

1. Run IMDS proxy for testing

    ```
    run-proxy
    ```

1. Verify if you get expected IAM Roles

    ```
    $ aws sts get-caller-identity
    {
        "UserId": "AROA4II6BDIS2CKJADTCY:test-session",
        "Account": "842413447717",
        "Arn": "arn:aws:sts::842413447717:assumed-role/ImdsProxyTestRole/test-session"
    }

    $ sudo aws sts get-caller-identity
    {
        "UserId": "AROA4II6BDIS7GQY4LYID:SageMaker",
        "Account": "842413447717",
        "Arn": "arn:aws:sts::842413447717:assumed-role/MySageMakerClusterInstanceRole/SageMaker"
    }
    ```

1. Verify that you have (or don't have) permissions

    ```
    $ aws s3 ls

    An error occurred (AccessDenied) when calling the ListBuckets operation: User: arn:aws:sts::842413447717:assumed-role/ImdsProxyTestRole/test-session is not authorized to perform: s3:ListAllMyBuckets because no identity-based policy allows the s3:ListAllMyBuckets action    
    ```

1. Make sure there is no direct access to the instance role

    This command should fail.

    ```
    make check-direct-access
    ```


#### Install this solution as a service

1. Install the solution as a systemd service

    ```
    make install-service
    ```

1. Enable and start the service

    ```
    make enable-service
    ```

1. Reboot the instance

    ```
    sudo reboot
    ```

1. Verify you get expected IAM roles

    ```
    $ aws sts get-caller-identity
    {
        "UserId": "AROA4II6BDIS2CKJADTCY:test-session",
        "Account": "842413447717",
        "Arn": "arn:aws:sts::842413447717:assumed-role/ImdsProxyTestRole/test-session"
    }

    $ sudo aws sts get-caller-identity
    {
        "UserId": "AROA4II6BDIS7GQY4LYID:SageMaker",
        "Account": "842413447717",
        "Arn": "arn:aws:sts::842413447717:assumed-role/MySageMakerClusterInstanceRole/SageMaker"
    }
    ```

#### Notes

- This solution assumes that you don't allow cluster users to login nodes as root user, and they don't have sudo priviledge.
- To actually use this solution, you need to modify the lifecycle script to install, enable and start the systemd services. Make sure you start the service before configuring SSSD and SlurmD.



