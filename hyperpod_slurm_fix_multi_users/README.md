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
    1. Download "create_user_with_id_on_head_node.sh” and "add_users_multi_nodes.sh" from this repo - this directory.
    1. Download add_users.sh script from the awsome-distributed-training repo.
        * https://github.com/aws-samples/awsome-distributed-training/blob/main/1.architectures/5.sagemaker-hyperpod/LifecycleScripts/base-config/add_users.sh
    1. Create “shared_users.txt”
        * Example:
            ``` text
            user1,1001,/fsx/user1
            user2,1002,/fsx/user2
            ```
       This file is used for 1) add_users_multi_nodes.sh to create users in worker nodes and login nodes, and 2) lifecycle script for new nodes.
    1. Place all these files somewhere under the `/fsx` (e.g., /fsx/ubuntu/adding-users)
    1. Run create_user_with_id_on_head_node.sh **on the head node**.
        * You will be prompted to enter user name, and user ID.
        * Repeat for all new users.
        * This step will create users **only on the head node**.
        * This step will also setup cross-node SSH login, and optionally add the users to sudoer.
    1. Modify add_users_multi_nodes.sh
        * Modify the variable `nodes`. Include worker nodes **and login nodes**.

            ``` bash
            nodes="ip-10-1-16-188,ip-10-1-75-77,ip-10-1-79-4"
            ```
    1. Run add_users_multi_nodes.sh script **on the head node**.
        * This step will create users you listed in the shared_users.txt, on all the nodes you listed in the variable `nodes`.
            
            ``` bash
            bash add_users_multi_nodes.sh
            ```

        * **Note:** This step doesn't add users to sudoer on each node. You need to do it manually as needed.

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

