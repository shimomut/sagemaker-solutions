## HyperPod Slurm - How to troubleshoot inconsistent user-IDs

### Final state

* User IDs have to be consistent across cluster nodes - Head node, Worker nodes, and Login nodes.
* When creating a new cluster and migrating shared file system (e.g., FSx Lustre) from previous cluster, the User IDs have to be same as the previous cluster.
* Home directory for each user (`/fsx/{user-name}`) and its contents are owned by the user.


### Find inconsistency

1. Login to head node, as “ubuntu” user  (or any sudoer user).
1. Get UserIDs from all nodes
    * Get user-ID on the current host

        ``` bash
        # Repeat this on head node and all login nodes
        id {user-name}
        
        # Get user-IDs from worker nodes
        srun -N 32 id {user-name}
        ```

    * Repeat this command for each user name.
1. Confirm UserIDs are not used by other users

    ``` bash
    getent passwd {user-id}
    
    srun -N 32 getent passwd {user-id}
    ```

1. Get shared_users.txt for the previous cluster.
1. Check if home directories exist for all users, and they and their contents are owned by correct users.
    
    ``` bash
    sudo ls -aln /fsx/{user-name}/
    ```

1. Based on the information above, identify which users have to be deleted/created.


### Fix the inconsistency

1. Login to head node, as “ubuntu” user (or any sudoer user).
1. Rename existing home directories.

    ``` bash
    sudo mv /fsx/{user-name} /fsx/_{user-name}.bak
    ```

1. Delete a user, without deleting the home directory
    * Delete a user on the current host
        
        ``` bash
        # Repeat this on head node and all login nodes
        sudo userdel {user-name}
        
        # Delete a user from all worker nodes
        srun -N 32 sudo userdel {user-name}
        ```

1. Create users
    1. Download “create-user-with-id.sh” script.
    1. Download add_users.sh script
        * https://github.com/aws-samples/awsome-distributed-training/blob/main/1.architectures/5.sagemaker-hyperpod/LifecycleScripts/base-config/add_users.sh
    1. Create “shared_users.txt”
        * Example:
            ``` text
            user1,1001,/fsx/user1
            user2,1002,/fsx/user2
            ```
    1. Run create-user-with-id.sh **on the head node**.
        * You will be prompted to enter user name, user ID and number of worker nodes.
        * Repeat for all new users.
        * This step will create users on the current host(= head node) and all worker nodes.
        * This step will also setup cross-node SSH login, and optionally add the users to sudoer.
        * **Note:** This step doesn’t create users on Login nodes.
    1. Run add_users.sh script **on login nodes**.
        * This step will create Create users in shared_users.txt, on the current host.
            
            ``` bash
            # Repeat this on all login nodes
            sudo bash add_users.sh
            ```

        * Repeat this step for each login node.

        * **Note:** This step doesn't add users to sudoer. You need to do it manually.

            ```
            sudo usermod -aG sudo {user-name}
            ```

1. Restore the contents of the backed-up home directory manually. Ownership of directories and files have to be manually fixed.

1. Upload “shared_users.txt” to the S3 bucket for lifecycle configuration script

    * Upload “shared_users.txt” to the S3 bucket for the lifecycle configuration script (next to "add_users.sh" script)
    * This step will make sure users listed in the “shared_users.txt” file are automatically created when new instances are created. (e.g., Scaling up cluster, Replacing unhealthy nodes, Upgrading cluster software)


### Verify

1. Follow [Find inconsistency section](#find-inconsistency) again.
1. Confirm you can login as the newly created users.
1. Confirm you can SSH across nodes as the newly created users.
1. Run some srun/sbatch commands as a newly created user.
1. Confirm home directories are owned by the correct users.
1. (Optional) Replace a worker node, and confirm that users are created in the new node.

