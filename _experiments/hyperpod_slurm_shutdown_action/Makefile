
install-services:
	sudo cp ./shutdown-action.sh /usr/local/bin/
	sudo cp ./shutdown-action.service /etc/systemd/system/
	sudo chmod 755 /usr/local/bin/shutdown-action.sh

enable-services:
	sudo systemctl daemon-reload
	sudo systemctl enable shutdown-action.service
	sudo systemctl start shutdown-action.service

disable-services:
	sudo systemctl stop shutdown-action.service
	sudo systemctl disable shutdown-action.service

service-status:
	systemctl status shutdown-action.service

check-executed:
	ls -al /home/ubuntu/shutdown-action-executed.txt

clear-executed:
	rm /home/ubuntu/shutdown-action-executed.txt
