from utils_host import HostSession
from utils_guest import GuestSession, GuestSessionV2
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
import re
import time
import os
project_file = os.path.dirname(os.path.dirname(os.path.dirname
                                           (os.path.dirname
                                            (os.path.dirname
                                             (os.path.abspath(__file__))))))
tmp_file = project_file


def run_case(params):
    src_host_ip = params.get('src_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))

    test = CreateTest(case_id='rhel7_11948_virtio_scsi_local', params=params)
    id = test.get_id()
    host_session = HostSession(id, params)

    test.main_step_log('1. create a data image.')
    image_format = params.get('image_format')
    drive_format = params.get('drive_format')
    if 'qcow2' in image_format:
        host_session.create_image('qemu-img create -f qcow2 %s/test1.img 15G'
                                  % tmp_file)
    elif 'raw' in image_format:
        host_session.create_image('qemu-img create -f raw %s/test1.img 15G'
                                  % tmp_file)

    test.main_step_log('2. start guest with this image as data image')
    params.vm_base_cmd_add('drive', 'id=device1,if=none,snapshot=off,'
                                    'aio=threads,cache=none,format=%s,'
                                    'file=%s/test1.img' % (image_format, tmp_file))
    if 'virtio-scsi' in drive_format:
        params.vm_base_cmd_add('device', 'scsi-hd,id=scsi-hd0,drive=device1,'
                                          'channel=0,scsi-id=10,lun=0')
    elif 'virtio-blk' in drive_format:
        params.vm_base_cmd_add('device',
                               'virtio-blk-pci,'
                               'drive=device1,'
                               'id=virtio-blk0')

    qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(cmd=qemu_cmd)
    serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    guest_ip = serial.serial_login()

    test.main_step_log('3. create a file in the device and record md5 value.')
    guest_session = GuestSession(case_id=id, params=params, ip=guest_ip)
    test.sub_step_log('3.1 check the disk status inside guest')
    data_disk_list = guest_session.get_data_disk()

    test.sub_step_log('3.2 mount this device to /mnt')
    guest_session.guest_cmd_output('mkfs.xfs %s' % data_disk_list[0])
    guest_session.guest_cmd_output('mount %s /mnt' % data_disk_list[0])
    guest_session.guest_cmd_output('mount | grep /mnt')

    test.sub_step_log('3.3 create a file to /mnt with dd')
    guest_session.guest_cmd_output(cmd='dd if=/dev/urandom '
                                       'of=/mnt/test1 bs=1M '
                                       'count=500 oflag=direct',
                                   timeout=600)

    test.sub_step_log('3.4 check the value md5sum of file')
    before_md5 = guest_session.guest_cmd_output('md5sum /mnt/test1 | awk {\'print $1\'}')

    test.main_step_log('4. block resize device1 20G')
    qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    qmp.qmp_cmd_output(
        '{ "execute": "block_resize", '
        '"arguments": { "device": "device1", "size": 21474836480 }}')
    if guest_session.guest_get_disk_size(dev=guest_session.get_data_disk()[0]) != '20G':
        test.test_error('Failed to block resize device1 to 20G')

    test.sub_step_log('4.1 check the value md5sum of file after block resize')
    after_md5 = guest_session.guest_cmd_output('md5sum /mnt/test1 | awk {\'print $1\'}')
    if after_md5 != before_md5:
        test.test_error('value md5 changed after block resize.')

    if 'raw' in image_format:
        test.main_step_log('5. block resize device1 10G')
        qmp.qmp_cmd_output(
            '{ "execute": "block_resize", '
            '"arguments": { "device": "device1", "size": 10737418240 }}')
        if guest_session.guest_get_disk_size(
                dev=guest_session.get_data_disk()[0]) != '10G':
            test.test_error('Failed to block resize device1 to 10G')

        test.sub_step_log('5.1 check the value md5sum of file after block resize')
        after_md5 = guest_session.guest_cmd_output('md5sum /mnt/test1 | awk {\'print $1\'}')
        if after_md5 != before_md5:
            test.test_error('value md5 changed after block resize.')

    guest_session.guest_dmesg_check()