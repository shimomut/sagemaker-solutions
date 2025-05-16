
#### How to use

1. Decide sender email address, and receiver email address.
1. Create the email identities for the email addresses (both for sender and receiver) on the SES management console.
1. Verify the email addresses.
1. Deploy the CloudFormation template. Specify the email addresses as the parameters.
1. Confirm that you can receive notification emails by changing the cluster status (e.g., scaling up/down).
    - For HyperPod EKS, you can test the node health notification by triggering instance replacement.
    - For HyperPod Slurm, as of 2025-05, you cannot test the node health notification. It comes when the node really got degraded at EC2 level.

#### Next steps

- You can customize the format of the email by modifying the Lambda function.
