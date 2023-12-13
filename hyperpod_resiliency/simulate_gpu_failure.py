import os
import getpass

assert getpass.getuser() == "root"

log_path = "/var/log/messages"
os.system(f'echo "Oct 12 08:25:03 localhost kernel: [  851.885993] NVRM: Xid (PCI:0000:10:1c): 74, pid=37407, NVLink: fatal error detected on link 0(0x0, 0x0, 0x10000, 0x0, 0x0, 0x0, 0x0)" >> {log_path}')
