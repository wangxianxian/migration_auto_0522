install
text
poweroff
lang en_US.UTF-8
keyboard us
network --onboot yes --device eth0 --bootproto dhcp
rootpw kvmautotest
firewall --enabled --ssh
selinux --enforcing
timezone --utc Asia/Shanghai
firstboot --disable
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr
clearpart --all --initlabel
autopart
xconfig --startxonboot
services --enable rc-local

%packages --ignoremissing
@core
@network-tools
lftp
ftp
vsftpd
gcc
gcc-c++
glibc-devel
glibc-static
patch
make
git
nc
net-tools
NetworkManager
ntpdate
redhat-lsb
numactl-libs
numactl
sg3_utils
hdparm
lsscsi
libaio-devel
perl-Time-HiRes
python-devel
flex
prelink
qemu-guest-agent
dracut-config-generic
iptables-services
-abrt*
-gnome-initial-setup
-gnome-boxes
scsi-target-utils
xfsprogs-devel
-strace32
popt-devel
ntp
telnet
telnet-server
xinetd
httpd
%end

%post
echo "OS install is completed" > /dev/ttyS0
echo "enable autologin" > /dev/ttyS0
sed -i '/daemon/ a \AutomaticLoginEnable=true\n\AutomaticLogin=root' /etc/gdm/custom.conf
echo "remove rhgb quiet by grubby" > /dev/ttyS0
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
grubby --args="biosdevname=0 net.ifnames=0" --update-kernel=$(grubby --default-kernel)
echo "dhclient" > /dev/ttyS0
dhclient
echo "get repo" > /dev/ttyS0
cat > /etc/yum.repos.d/epel.repo << EOF
# Please input your repos url.
EOF
echo "yum makecache" > /dev/ttyS0
yum makecache
echo "yum install -y stress" > /dev/ttyS0
yum install -y stress
echo "chkconfig sshd on" > /dev/ttyS0
chkconfig sshd on
echo "chkconfig iptables on" > /dev/ttyS0
chkconfig iptables on
echo "iptables -F" > /dev/ttyS0
iptables -F
echo "echo 0 > selinux/enforce" > /dev/ttyS0
echo 0 > /selinux/enforce
echo "chkconfig NetworkManager on" > /dev/ttyS0
chkconfig NetworkManager on
echo "update ifcfg-*" > /dev/ttyS0
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-*
sed -i "/UUID/d" /etc/sysconfig/network-scripts/ifcfg-*
sed -i "s/^/#/g" /usr/lib/udev/rules.d/80-net-name-slot.rules
echo "Disable lock cdrom udev rules" > /dev/ttyS0
sed -i "/--lock-media/s/^/#/" /usr/lib/udev/rules.d/60-cdrom_id.rules 2>/dev/null>&1
echo "ifconfig -a | tee /dev/ttyS0" >> /etc/rc.local
echo "iptables -F">> /etc/rc.local
chmod +x /etc/rc.local
ln -sf /etc/rc.local /etc/rc.d/rc.local
echo 'Post set up finished' > /dev/ttyS0
echo Post set up finished > /dev/tty0
echo Post set up finished > /dev/hvc0
%end
