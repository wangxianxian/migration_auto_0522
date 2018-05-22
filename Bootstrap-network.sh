#!/bin/bash

unalias -a
trap "_exit" 1 2 3 15

_usage()
{
    echo "Usage: sh Bootstrap-network.sh [bound-interface]"
}

# set an initial value for the flag
QUIET=false
VERBOSE=true

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

if [ $1 ]
then
    _exec_cmd "ls /etc/sysconfig/network-scripts/ifcfg-$1"
    _exit_on_error "No such device '$1', please check again."
    _log_info "Adding a bridge device to network."
    sed -i 's/^BOOTPROTO=dhcp$/BOOTPROTO=none/g' /etc/sysconfig/network-scripts/ifcfg-$1
    sed -i 's/^BOOTPROTO="dhcp"$/BOOTPROTO="none"/g' /etc/sysconfig/network-scripts/ifcfg-$1
    echo "BRIDGE=switch" >>/etc/sysconfig/network-scripts/ifcfg-$1
    echo "DEVICE=switch
BOOTPROTO=dhcp
ONBOOT=yes
TYPE=Bridge" >>/etc/sysconfig/network-scripts/ifcfg-br0
    _log_info "Restart the network service."
    _exec_cmd "service network restart"
else
    _usage
fi