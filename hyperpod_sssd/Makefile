all:

install-apt-pkgs:
	sudo apt install sssd ldap-utils sssd-tools

run:
	python3 ./lcc/configure_sssd.py --node-type controller

check1:
	getent passwd user1@cluster-test.amazonaws.com

check2:
	getent passwd user1

check3:
	id user1

check4:
	su -l user1@cluster-test.amazonaws.com

check5:
	sssctl domain-status cluster-test.amazonaws.com

clear-cache:
	sudo sssctl cache-remove

obfuscate:
	python3 ./tools/obfuscate_password.py

upload-lcc:
	aws s3 sync ./lcc s3://sagemaker-cluster-842413447717/lcc/sssd/
