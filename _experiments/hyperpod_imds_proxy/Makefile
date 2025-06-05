
list-iptables:
	sudo iptables -t nat -L OUTPUT --line-numbers

list-iptables-all:
	sudo iptables-save

remove-original-iptables-entry:
	sudo iptables -t nat -D OUTPUT -d 169.254.169.254 -p tcp --dport 80 -j DNAT --to-destination 169.254.0.2:9081

revive-original-iptables-entry:
	sudo iptables -t nat -I OUTPUT 1 -d 169.254.169.254 -p tcp --dport 80 -j DNAT --to-destination 169.254.0.2:9081

add-proxy-iptables-entries:
	sudo iptables -t nat -I OUTPUT 1 -d 169.254.169.254 -p tcp --dport 80 -m owner --uid-owner 0 -j DNAT --to-destination 169.254.0.2:9081
	sudo iptables -t nat -I OUTPUT 1 -d 169.254.169.254 -p tcp --dport 80 -m owner ! --uid-owner 0 -j DNAT --to-destination 127.0.0.1:8080

remove-proxy-iptables-entries:
	sudo iptables -t nat -D OUTPUT -d 169.254.169.254 -p tcp --dport 80 -m owner --uid-owner 0 -j DNAT --to-destination 169.254.0.2:9081
	sudo iptables -t nat -D OUTPUT -d 169.254.169.254 -p tcp --dport 80 -m owner ! --uid-owner 0 -j DNAT --to-destination 127.0.0.1:8080

block-direct-access-to-sagemaker-role:
	sudo iptables -A OUTPUT -d 169.254.0.2 -p tcp --dport 9081 -m owner ! --uid-owner 0 -j DROP

unblock-direct-access-to-sagemaker-role:
	sudo iptables -D OUTPUT -d 169.254.0.2 -p tcp --dport 9081 -m owner ! --uid-owner 0 -j DROP



run-proxy:
	sudo python3 imds_proxy_server.py


check-direct-access:
	export TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"` && \
	curl -H "X-aws-ec2-metadata-token: $$TOKEN" http://169.254.0.2:9081/latest/meta-data/iam/security-credentials/XyzRole


install-services:
	sudo cp ./imds-proxy-iptables.sh /usr/local/bin/
	sudo cp ./imds-proxy-server.py /usr/local/bin/
	sudo cp ./imds-proxy-iptables.service /etc/systemd/system/
	sudo cp ./imds-proxy-server.service /etc/systemd/system/
	sudo chmod 755 /usr/local/bin/imds-proxy-iptables.sh
	sudo chmod 644 /usr/local/bin/imds-proxy-server.py

enable-services:
	sudo systemctl daemon-reload
	sudo systemctl enable imds-proxy-server.service
	sudo systemctl start imds-proxy-server.service
	sudo systemctl enable imds-proxy-iptables.service
	sudo systemctl start imds-proxy-iptables.service

disable-services:
	sudo systemctl stop imds-proxy-server.service
	sudo systemctl disable imds-proxy-server.service
	sudo systemctl stop imds-proxy-iptables.service
	sudo systemctl disable imds-proxy-iptables.service

service-status:
	systemctl status imds-proxy-iptables.service
	@echo ""
	@echo "-----------------------"
	@echo ""
	systemctl status imds-proxy-server.service

