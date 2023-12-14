all:

backup-config:
	sudo cp /etc/sssd/sssd.conf ./sssd.conf.bak
	sudo chown ubuntu:ubuntu ./sssd.conf.bak

	sudo cp /etc/krb5.conf ./krb5.conf.bak
	sudo chown ubuntu:ubuntu ./krb5.conf.bak

install-config:
	sudo cp ./sssd.conf /etc/sssd/sssd.conf
	sudo chmod 600 /etc/sssd/sssd.conf

	sudo cp ./krb5.conf /etc/krb5.conf
	sudo chmod 644 /etc/krb5.conf

restart-service:
	sudo systemctl restart sssd.service

service-status:
	sudo systemctl status sssd.service

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
