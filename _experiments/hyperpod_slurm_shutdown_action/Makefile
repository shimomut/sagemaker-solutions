local-test:
	sudo python3 ./shutdown-action.py

install-services:
	sudo cp ./shutdown-action.py /usr/local/bin/
	sudo cp ./shutdown-action.service /etc/systemd/system/
	sudo chmod 644 /usr/local/bin/shutdown-action.py

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
	ls -al /fsx/ubuntu/shutdown-action-data

clear-executed:
	sudo rm /fsx/ubuntu/shutdown-action-data/*.txt
