# https://docs.aws.amazon.com/fsx/latest/LustreGuide/performance.html#performance-tips

sudo lctl get_param osc.*.max_dirty_mb

sudo lctl get_param ldlm.namespaces.*.lru_max_age
sudo lctl get_param ldlm.namespaces.*.lru_size

sudo cat /etc/modprobe.d/modprobe.conf

sudo lctl get_param osc.*OST*.max_rpcs_in_flight
sudo lctl get_param mdc.*.max_rpcs_in_flight
sudo lctl get_param mdc.*.max_mod_rpcs_in_flight