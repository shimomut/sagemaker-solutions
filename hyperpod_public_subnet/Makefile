create-and-attach-eips:
	python3 hyperpod_public_subnet.py create-and-attach-eips

delete-unused-eips:
	python3 hyperpod_public_subnet.py delete-unused-eips

switch-to-public:
	python3 hyperpod_public_subnet.py switch-to-public

switch-to-private:
	python3 hyperpod_public_subnet.py switch-to-private

verify-no-nat:
	@echo "Checking that nodes are using EIPs (not NAT Gateway)..."
	@echo ""
	@echo "Attached EIPs (from our script):"
	@python3 -c "\
	import boto3; \
	from config import Config; \
	from hyperpod_public_subnet import extract_components_from_cluster_arn, list_eips; \
	extract_components_from_cluster_arn(); \
	ec2 = boto3.client('ec2', region_name=Config.region); \
	eips = list_eips(ec2); \
	ips = set(); \
	[ips.add(e['PublicIp']) for e in eips.values()]; \
	print('\n'.join(sorted(ips))); \
	open('/tmp/_hyperpod_eips.txt','w').write('\n'.join(sorted(ips)))"
	@echo ""
	@echo "Outbound IPs (from pods on each node):"
	@for node in $$(kubectl get nodes -o jsonpath='{.items[*].metadata.name}'); do \
		outbound_ip=$$(kubectl run --rm -i --restart=Never --image=curlimages/curl \
			--overrides="{\"spec\":{\"nodeName\":\"$$node\",\"tolerations\":[{\"operator\":\"Exists\"}]}}" \
			verify-nat-$$RANDOM -- -s ifconfig.me 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1); \
		if grep -qx "$$outbound_ip" /tmp/_hyperpod_eips.txt 2>/dev/null; then \
			echo "  $$node: $$outbound_ip (matches EIP - OK)"; \
		else \
			echo "  $$node: $$outbound_ip (NOT in EIP list - likely using NAT)"; \
		fi; \
	done
	@rm -f /tmp/_hyperpod_eips.txt

clean:
	python3 hyperpod_public_subnet.py clean
