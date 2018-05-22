#!/usr/bin/env bash
unalias -a
trap "_exit" 1 2 3 15

read -p "please input the src host ip:" src_host_ip
read -p "please input the dst host ip:" dst_host_ip
read -p "please input the share_images_dir:" share_images_dir

_usage()
{
    echo "Usage: sh Bootstrap-migration.sh [destination ip]"
}

# set an initial value for the flag
QUIET=false
VERBOSE=true
PASSWD="kvmautotest"

_log()          { if ! $QUIET; then echo -e $*; fi; }
_log_info()     { _log "\033[32mINFO\033[0m\t" $*; }
_log_warn()     { _log "\033[33mWARN\033[0m\t" $*; }
_log_error()    { _log "\033[31mERROR\033[0m\t" $*; }

_within_dir()   { pushd . >/dev/null; cd $1; }
_go_back()      { popd >/dev/null; }

_exit()
{
    local RET=${1:-0}
    if [ $RET -ne 0 ]; then
        _log "Please handle the ERROR(s) and re-run this script"
    fi
    exit $RET
}
_exit_on_error() { if [ $? -ne 0 ]; then _log_error $*; _exit 1; fi; }
_warn_on_error() { if [ $? -ne 0 ]; then _log_warn $*; fi; }

_exec_cmd()
{
    local CMD=$*
    if $QUIET || (! $VERBOSE); then
        eval "$CMD" &>/dev/null
    else
        _log "\033[1m=> $CMD\033[0m"
        eval "$CMD"
    fi
    return $?
}


if [ ! -n "$dst_host_ip" ]
then
    _log_error "Please specify a destination ip."
    _usage
    exit 1
else
    _log "ssh-copy-id to destination host"
    _exec_cmd "sshpass -p $PASSWD ssh-copy-id -o \"StrictHostKeyChecking no\" -i /root/.ssh/id_rsa.pub root@$dst_host_ip"
    _exit_on_error "Failed to ssh-copy-id to destination host"

    _log "update the clock of destination host"
    _exec_cmd "ssh root@$dst_host_ip ntpdate clock.redhat.com"
    _exit_on_error "Failed to update the clock of destination host"

    _log "update the clock of local host"
    _exec_cmd "ntpdate clock.redhat.com"
    _exit_on_error "Failed to update the clock of local host"

    _log "flush iptables rules of local host"
    _exec_cmd "iptables -F"
    _exit_on_error "Failed to update the clock of local host"

    _log "flush iptables rules of destination host"
    _exec_cmd "ssh root@$dst_host_ip iptables -F"
    _exit_on_error "Failed to update the clock of destination host"

    _log "configure nfs of local host"
    _exec_cmd "mkdir -p $share_images_dir"
    _exec_cmd "echo $share_images_dir *\(rw,sync,no_root_squash\) > /etc/exports"
    _exec_cmd "systemctl start nfs"
    _exec_cmd "systemctl restart nfs"
    _exec_cmd "systemctl status nfs"
    _exit_on_error "Failed to start nfs service"

    _log "mount src dir to destination host"
    _exec_cmd "ssh root@$dst_host_ip mkdir -p $share_images_dir"
    _exec_cmd "ssh root@$dst_host_ip umount $share_images_dir"
    _exec_cmd "ssh root@$dst_host_ip mount -t nfs $src_host_ip:$share_images_dir $share_images_dir"
    _exit_on_error "Failed to mount src dir to destination host"

    _log "Install bridge-utils"
    _exec_cmd "ssh root@$dst_host_ip yum install -y bridge-utils"
    _exit_on_error "Failed to install bridge-utils on $dst_host_ip"

    _log "Copy qemu-ifup/ifdown script to destination host"
    _exec_cmd "scp /etc/qemu-if* $dst_host_ip:/etc/"
    _exit_on_error "Failed to copy qemu-ifup/ifdown script to $dst_host_ip"
fi
