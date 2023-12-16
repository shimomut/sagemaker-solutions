all:

run:
	python3 ./lcc/configure_sssd.py

backup-config:
	sudo cp /etc/sssd/sssd.conf ./config/sssd.conf
	sudo chown ubuntu:ubuntu ./config/sssd.conf

	sudo cp /etc/krb5.conf ./config/krb5.conf
	sudo chown ubuntu:ubuntu ./config/krb5.conf

check1:
	getent passwd user1@cluster-test.amazonaws.com

check2:
	getent passwd user1

check3:
	id user1

check4:
	su -l user1@cluster-test.amazonaws.com

check5:
	sssctl domain-status cluster-test3.amazonaws.com

clear-cache:
	sudo sssctl cache-remove

obfuscate:
	sudo sss_obfuscate -d cluster-test3.amazonaws.com
