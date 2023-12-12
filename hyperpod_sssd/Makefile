all:

backup-config:
	sudo cp /etc/sssd/sssd.conf ./sssd.conf.bak
	sudo chown ubuntu:ubuntu ./sssd.conf.bak

install-config:
	sudo cp ./sssd.conf /etc/sssd/sssd.conf
	sudo chmod 600 /etc/sssd/sssd.conf

restart-service:
	sudo systemctl restart sssd.service

service-status:
	sudo systemctl status sssd.service

check:
	getent passwd user1@cluster-test.amazonaws.com

check2:
	getent passwd user1

check3:
	id user1