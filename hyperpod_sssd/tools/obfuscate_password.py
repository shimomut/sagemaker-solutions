import sys
import getpass

import pysss


reader_pw = getpass.getpass("AD reader user password: ").strip()
if not reader_pw:
    print("Invalid password")
    sys.exit(1)

print(pysss.password().encrypt(reader_pw, pysss.password().AES_256))
