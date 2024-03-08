import getpass
import pysss

admin_pw = getpass.getpass("AD Admin password: ")

print(pysss.password().encrypt(admin_pw, pysss.password().AES_256))
