set -ex

# https://docs.aws.amazon.com/fsx/latest/LustreGuide/performance.html#performance-tips

sudo lctl set_param osc.*.max_dirty_mb=64

sudo lctl set_param ldlm.namespaces.*.lru_max_age=600000
sudo lctl set_param ldlm.namespaces.*.lru_size=9600

echo "options ptlrpc ptlrpcd_per_cpt_max=32" >> /etc/modprobe.d/modprobe.conf
echo "options ksocklnd credits=2560" >> /etc/modprobe.d/modprobe.conf

# reload all kernel modules to apply the above two settings
#sudo reboot

# Instead of rebooting.
sudo lustre_rmmod
sudo modprobe lustre

sudo lctl set_param osc.*OST*.max_rpcs_in_flight=32
sudo lctl set_param mdc.*.max_rpcs_in_flight=64
sudo lctl set_param mdc.*.max_mod_rpcs_in_flight=50

# for P5
NIC=enp74s0
sudo lnetctl lnet configure
sudo lnetctl net del --net tcp
sudo lnetctl net add --net tcp --if $NIC --cpt 0
sudo ethtool -G $NIC rx 8192
