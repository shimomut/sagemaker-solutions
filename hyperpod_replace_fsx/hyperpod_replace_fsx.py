
fstab_path = "/etc/fstab"
remount_script_path = "/opt/ml/scripts/check_mount.sh"


class FsxLustreInfo:
    def __init__(self, dns_name, mount_name):
        self.dns_name = dns_name
        self.mount_name = mount_name

fsxl_old = FsxLustreInfo( "fs-0a97c6b8b75f3bfe7.fsx.us-west-2.amazonaws.com", "vchi7bev" )
fsxl_new = FsxLustreInfo( "fs-093d4d1ba5b316e6c.fsx.us-west-2.amazonaws.com", "jyd6bbev" )


def replace_fsxl_info(filename):

    print(f"Updating {filename}")

    with open(filename) as fd:
        s = fd.read()
        s = s.replace(fsxl_old.dns_name, fsxl_new.dns_name)
        s = s.replace(fsxl_old.mount_name, fsxl_new.mount_name)

    with open(filename,"w") as fd:
        fd.write(s)


def main():
    replace_fsxl_info(fstab_path)
    replace_fsxl_info(remount_script_path)


if __name__ == "__main__":
    main()
