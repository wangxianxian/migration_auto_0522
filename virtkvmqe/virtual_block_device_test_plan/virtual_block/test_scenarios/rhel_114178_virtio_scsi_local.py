from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
import re
import time

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))

    test = CreateTest(case_id='rhel_114178_virtio_scsi_local', params=params)
    id = test.get_id()
    host_session = HostSession(id, params)

    test.main_step_log('1. Create qcow2 image with backing file '
                       'while specifying backing store format')

    host_session.create_image('qemu-img create -f raw /tmp/backing.raw 64M')
    host_session.create_image(
        'qemu-img create -f qcow2 -F raw -b /tmp/backing.raw /tmp/test.qcow2')

    test.main_step_log(
        '2. Try to start qemu while specifying the chain manually via -blockdev')

    params.vm_base_cmd_add(
        'blockdev', 'driver=file,filename=/tmp/backing.raw,node-name=backing')

    params.vm_base_cmd_add(
        'blockdev', 'driver=qcow2,file.driver=file,file.filename=/tmp/test.qcow2,node-name=root,backing=backing')

    qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(qemu_cmd)

    test.sub_step_log('Connecting to serial')
    serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    vm_ip = serial.serial_login()

    guest_session = GuestSession(vm_ip, id, params)
    guest_session.guest_cmd_output('lsblk')
    guest_session.guest_cmd_output('lsscsi')

    serial.serial_shutdown_vm()
