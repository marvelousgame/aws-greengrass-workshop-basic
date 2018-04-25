#!/bin/sh

#
# gg-prep-ec2.sh
# prepares an Amazon EC2 instance with Amazon Linux for
# use with AWS Greengrass
#


if ! uname -r |grep amzn ; then
    echo "this seems not to be an Amazon Linux AMI, exiting"
    exit 1
fi

if [ $(whoami) != "root" ]; then
    echo "$0 must be run as root"
    echo "try: sudo ./$0"
    exit 1
fi


if [ ! -d /greengrass ]; then
    echo "directory /greengrass does not exist"
    echo "unpack the greengrass software first with the following command:"
    echo "sudo tar -zxvf greengrass-platform-version.tar.gz -C /"
    exit 1
fi

echo "-> ggc_user"
if ! getent passwd ggc_user; then
    echo "adding ggc_user"
    useradd -r ggc_user
fi
echo "------------------------------"

echo "-> ggc_group"
if ! getent group ggc_group; then
    echo "adding ggc_group"
    groupadd -r ggc_group
fi
echo "------------------------------"


echo "-> hardlink and symlink protection"
if [ -e /etc/sysctl.d/00-defaults.conf ]; then
    if ! grep '^fs.protected_hardlinks\s*=\s*1' /etc/sysctl.d/00-defaults.conf; then
        echo 'fs.protected_hardlinks = 1' >> /etc/sysctl.d/00-defaults.conf
    fi
    if ! grep '^fs.protected_symlinks\s*=\s*1' /etc/sysctl.d/00-defaults.conf; then
        echo 'fs.protected_symlinks = 1' >> /etc/sysctl.d/00-defaults.conf
    fi
else
    echo '# AWS Greengrass' >> /etc/sysctl.d/00-defaults.conf
    echo 'fs.protected_hardlinks = 1' >> /etc/sysctl.d/00-defaults.conf
    echo 'fs.protected_symlinks = 1' >> /etc/sysctl.d/00-defaults.conf
fi

sysctl -p
echo "------------------------------"

echo "-> cgroup mount in /etc/fstab"
if ! grep '^cgroup\s*/sys/fs/cgroup\s*cgroup\s*defaults\s*0\s*0' /etc/fstab; then
    echo "# AWS Greengrass" >> /etc/fstab
    echo "cgroup /sys/fs/cgroup cgroup defaults 0 0" >> /etc/fstab
fi
echo "------------------------------"

cd /tmp/

echo "-> VeriSign root CA cert"
curl https://www.symantec.com/content/en/us/enterprise/verisign/roots/VeriSign-Class%203-Public-Primary-Certification-Authority-G5.pem > root-ca.pem
if [ -d /greengrass/configuration/certs/ ]; then
  cp root-ca.pem /greengrass/configuration/certs/
fi

if [ -d /greengrass/certs/ ]; then
  cp root-ca.pem /greengrass/certs/root.ca.pem
  cd /greengrass/certs/ && ln -s root.ca.pem root-ca.pem
  cd /tmp/
fi

echo "------------------------------"

echo "-> cgroupfs-mount"
curl https://raw.githubusercontent.com/tianon/cgroupfs-mount/master/cgroupfs-mount > cgroupfs-mount

chmod +x cgroupfs-mount
./cgroupfs-mount
echo "------------------------------"

echo "-> packages: sqlite, telnet, jq"
yum -y install sqlite telnet jq strace git tree

echo "-> upgrading pip, installing python packages"
PATH=$PATH:/usr/local/bin
pip install --upgrade pip
hash -r
pip install AWSIoTPythonSDK
pip install urllib3

echo "Reboot required!"
echo "Hit any key to reboot, Ctrl+C to abort"
read
init 6
