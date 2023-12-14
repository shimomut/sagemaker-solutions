all:

backup-config:
	sudo cp /etc/sssd/sssd.conf ./sssd.conf.bak
	sudo chown ubuntu:ubuntu ./sssd.conf.bak

install-config:
	sudo cp ./sssd.conf /etc/sssd/sssd.conf
	sudo chmod 600 /etc/sssd/sssd.conf

	sudo cp ./krb5.conf /etc/krb5.conf
	sudo chmod 644 /etc/krb5.conf

install-config-join:
	sudo cp ./sssd-4.conf /etc/sssd/sssd.conf
	sudo chmod 600 /etc/sssd/sssd.conf

install-config-blog:
	sudo cp ./sssd-5.conf /etc/sssd/sssd.conf
	sudo chmod 600 /etc/sssd/sssd.conf

restart-service:
	sudo systemctl restart sssd.service

service-status:
	sudo systemctl status sssd.service

check1:
	getent passwd user1@cluster-test.amazonaws.com
	getent passwd user2@cluster-test.amazonaws.com

check2:
	getent passwd user1
	getent passwd user2

check3:
	id user1
	id user2

check4:
	su -l user1@cluster-test.amazonaws.com

check5:
	sssctl domain-status cluster-test.amazonaws.com