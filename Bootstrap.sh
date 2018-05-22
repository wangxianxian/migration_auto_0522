#!/bin/bash

unalias -a
trap "_exit" 1 2 3 15

BASE_DIR="$(cd $(dirname $0) && pwd)"

RPM_REQS=(
    "gcc" "glibc-headers" "python-devel" "nc|nmap-ncat" "iproute" "iputils"
    "tcpdump" "p7zip" "gstreamer1-plugins-good|gstreamer-plugins-good"
    "pygobject2|gstreamer-python" "bridge-utils" "genisoimage"
    "httpd" "nfs-utils" "ntp" "sysstat" "perl-ExtUtils-MakeMaker"
    "vsftpd" "xinetd" "targetcli|scsi-target-utils" "telnet" "telnet-server"
    "lynx" "mtools" "xz-devel" "bzip2" "openssl-devel" "libffi-devel" "glib2-devel"
    "libtool" "libjpeg-turbo-devel" "make"
    )

_usage()
{
    echo "Usage: python Start2Run.py [OPTION]"
}

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

# check if a python pkg exits using pip list
_has_pypkg() { _exec_cmd "pip list | grep -F $1"; return $?; }

_uninstall_pypkg()
{
    local pkg=$1; shift
    if _has_pypkg "$pkg"; then
        _exec_cmd "pip uninstall -y $pkg"
        _exit_on_error "Failed to uninstall pypkg $pkg"
    fi
}

_has_cmd()      { _exec_cmd "command -v $1"; return $?; }
_has_rpm()      { _exec_cmd "rpm -q $1"; return $?; }

_chk_component()
{
    for RPM in ${1//|/ }; do
        _has_rpm "$RPM" && return 0
        _exec_cmd "yum install -y $RPM"
        if [ $? -eq 0 ]; then
            _log_info "Installed component '$RPM'"
            return 0
        fi
    done
    return 1
}

_get_release_ver()
{
    cat /etc/redhat-release | grep -oE '[0-9]+\.[0-9]+'
}

REL_X_VER="$(_get_release_ver | cut -d'.' -f1)"

_get_relpath()  { realpath --relative-to=$2 $1; }
_find_path()    { find ${2:-$PWD} -name $1 | grep -oE '.+'; }

_create_qemu_if_script()
{
    _exec_cmd "ls /etc/qemu-ifup"
    if [ $? -ne 0 ]; then
        _log_info "Create qemu-ifup script"
        _exec_cmd "touch /etc/qemu-ifup"
        echo -e '#!/bin/sh
switch=switch
/sbin/ifconfig $1 0.0.0.0 up
/usr/sbin/brctl addif ${switch} $1
/usr/sbin/brctl setfd ${switch} 0
/usr/sbin/brctl stp ${switch} off' >>/etc/qemu-ifup
    fi
    _exec_cmd "ls /etc/qemu-ifdown"
    if [ $? -ne 0 ]; then
        _log_info "Create qemu-ifdown script"
        _exec_cmd "touch /etc/qemu-ifdown"
        echo -e '#!/bin/sh
switch=switch
/sbin/ifconfig $1 0.0.0.0 down
/usr/sbin/brctl delif ${switch} $1' >>/etc/qemu-ifdown
    fi
    _exec_cmd "chmod +x /etc/qemu-if*"
}

_pre_install()
{
    _create_qemu_if_script
    if ! _has_cmd "brew"; then
        _log_info "Installing brewkoji"
        _exec_cmd "curl -L" \
            "http://download.devel.redhat.com/rel-eng/RCMTOOLS/rcm-tools-rhel-${REL_X_VER}-server.repo" \
            "-o /etc/yum.repos.d/rcm-tools.repo && yum install -y brewkoji"
        _exit_on_error "Failed to install brewkoji"
    fi

    if ! _has_rpm "epel-release"; then
        _log_info "Installing epel-release"
        _exec_cmd "yum install -y" \
            "https://dl.fedoraproject.org/pub/epel/epel-release-latest-${REL_X_VER}.noarch.rpm"
        _warn_on_error "Failed to install epel-release, this may result errors"
    fi

    _log_info "Checking required components"
    for COMP in ${RPM_REQS[@]}; do
        _chk_component "$COMP"
        _exit_on_error "Failed to install the missing component '$COMP'"
    done

    if ! _has_cmd "pip"; then
        _log_info "Installing pip"
        _exec_cmd "yum install -y python-pip" || {
            _exec_cmd "curl -kL https://bootstrap.pypa.io/get-pip.py" \
                "-o get-pip.py"
            _exec_cmd "python get-pip.py"
        }
        _exit_on_error "Failed to install pip"
    fi

    PYV=`python -c "import sys;t='{v[0]}.{v[1]}'.format(v=list(sys.version_info[:2]));sys.stdout.write(t)";`
    if [ "$PYV" == "2.6" ]; then
        # python 2.6 setuptools and wheel need specific versions
        # otherwise, installation of requirements-py26.txt will fail
        _exec_cmd "pip install wheel==0.29.0"
        _exec_cmd "pip install setuptools==33.1.1"
    else
        _exec_cmd "pip install setuptools==39.0.1"
    fi

    _log_info "Install tool sshpass"
    _exec_cmd "wget http://sourceforge.net/projects/sshpass/files/sshpass/1.05/sshpass-1.05.tar.gz"
    _exec_cmd "tar -xvf sshpass-1.05.tar.gz"
    _exec_cmd "cd sshpass-1.05/; ./configure; make; make install"
    _exec_cmd "sshpass -V"
    _exit_on_error "Failed to install sshpass"

    _log_info "Generate ssh key"
    _exec_cmd "yes | ssh-keygen -t rsa -N \"\" -f ~/.ssh/id_rsa"
    _exit_on_error "Failed to generate ssh key"
}

_install()
{

    _exec_cmd "pip install -r $BASE_DIR/requirements.txt"
    _exit_on_error "Failed to install mouse's requirements"

}

# set an initial value for the flag
QUIET=false
VERBOSE=true

_pre_install
_install
_log_info "***Install all package required successfully***"
_log_info "***Now, you could start to run with \"python Start2Run.py\"***"
_exit
