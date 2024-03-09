import sys
import getpass

import pysss


admin_pw = getpass.getpass("AD Admin password: ").strip()
if not admin_pw:
    print("Invalid password")
    sys.exit(1)

print(pysss.password().encrypt(admin_pw, pysss.password().AES_256))
