
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
	sudo python3 imds_proxy.py


check-direct-access:
	export TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"` && \
	curl -H "X-aws-ec2-metadata-token: $$TOKEN" http://169.254.0.2:9081/latest/meta-data/iam/security-credentials/XyzRole


install-as-systemd-service:
	sudo cp ./imds_proxy_service.sh /usr/local/bin/
	sudo cp ./imds_proxy.py /usr/local/bin/
	sudo chmod +x /usr/local/bin/imds_proxy_service.sh
	sudo cp ./imds_proxy.service /etc/systemd/system/

enable-and-start-service:
	sudo systemctl daemon-reload
	sudo systemctl enable imds_proxy.service
	sudo systemctl start imds_proxy.service

service-status:
	systemctl status imds_proxy.service

