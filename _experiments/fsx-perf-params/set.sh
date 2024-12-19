set -ex

# https://docs.aws.amazon.com/fsx/latest/LustreGuide/performance.html#performance-tips

# Run this script with sudo.

lctl set_param osc.*.max_dirty_mb=64

lctl set_param ldlm.namespaces.*.lru_max_age=600000
lctl set_param ldlm.namespaces.*.lru_size=9600

echo "options ptlrpc ptlrpcd_per_cpt_max=32" >> /etc/modprobe.d/modprobe.conf
echo "options ksocklnd credits=2560" >> /etc/modprobe.d/modprobe.conf

# reload all kernel modules to apply the above two settings
# reboot

# Instead of rebooting.
umount /fsx
lustre_rmmod
modprobe lustre
mount /fsx

lctl set_param osc.*OST*.max_rpcs_in_flight=32
lctl set_param mdc.*.max_rpcs_in_flight=64
lctl set_param mdc.*.max_mod_rpcs_in_flight=50

# for P5
NIC=enp74s0
lnetctl lnet configure
lnetctl net del --net tcp
lnetctl net add --net tcp --if $NIC --cpt 0
ethtool -G $NIC rx 8192
