
list-iptables:
	sudo iptables -t nat -L OUTPUT --line-numbers

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


run-proxy:
	sudo python3 imds_proxy.py

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

