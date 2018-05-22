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

    test = CreateTest(case_id='rhel7_11911_virtio_scsi_local', params=params)
    id = test.get_id()
    host_session = HostSession(id, params)
    test.main_step_log('1. prepare a installed guest.')

    test.main_step_log('2. create a data disk.')
    image_format = params.get('image_format')
    drive_format = params.get('drive_format')
    if 'qcow2' in image_format:
        host_session.create_image('qemu-img create -f qcow2 %s/test1.img 100G'
                                  % tmp_file)
    elif 'raw' in image_format:
        host_session.create_image('qemu-img create -f raw %s/test1.img 100G'
                                  % tmp_file)

    test.main_step_log('3. boot a guest attached data disk created by step 2.')
    params.vm_base_cmd_add('drive', 'id=drive_data0,if=none,snapshot=off,'
                                    'aio=threads,cache=none,format=%s,'
                                    'file=%s/test1.img' % (image_format, tmp_file))
    if 'virtio-scsi' in drive_format:
        params.vm_base_cmd_add('device', 'scsi-hd,id=scsi-hd0,drive=drive_data0,'
                                          'channel=0,scsi-id=10,lun=0')
    elif 'virtio-blk' in drive_format:
        params.vm_base_cmd_add('device',
                               'virtio-blk-pci,'
                               'drive=drive_data0,'
                               'id=virtio-blk0')

    qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(cmd=qemu_cmd)
    serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    guest_ip = serial.serial_login()

    test.main_step_log('4. in guest: # mkfs.ext4 /dev/[vs]db '
                       '# mount /dev/[vs]db /mnt '
                       '# dd if=/dev/zero of=/mnt/test1 '
                       'bs=4k count=1000 oflag=direct')
    guest_session = GuestSession(case_id=id, params=params, ip=guest_ip)
    test.sub_step_log('4.1 check the disk status inside guest')
    data_disk_list = guest_session.get_data_disk()

    guest_session.guest_cmd_output('mkfs.xfs %s' % data_disk_list[0])
    guest_session.guest_cmd_output('mount %s /mnt' % data_disk_list[0])
    guest_session.guest_cmd_output('mount | grep /mnt')

    guest_session.guest_cmd_output(cmd='dd if=/dev/zero '
                                       'of=/mnt/test1 bs=4k '
                                       'count=1000 oflag=direct',
                                   timeout=600)

    test.main_step_log('5. repeat step 4 using bs=8k / '
                       '16k / 32k/ 64k / 128k / 256k')
    bs_size_list = ['8k', '16k', '32k', '64k', '128k', '256k']
    for bs_size in bs_size_list:
        guest_session.guest_cmd_output(cmd='dd if=/dev/zero '
                                           'of=/mnt/test1 bs=%s '
                                           'count=1000 oflag=direct'
                                           % bs_size, timeout=600)

    guest_session.guest_cmd_output('umount /mnt')

    test.main_step_log('6. start multi dd progress at the same time.'
                       '- write 8 partition with '
                       'bs= 4k/8k/16k/64k/128k/256k/4M/1G at the same time, '
                       '- read 8 partition with '
                       'bs= 4k/8k/16k/64k/128k/256k/4M/1G at the same time')

    guest_session.guest_create_parts(dev=data_disk_list[0], num=8)

    data_disk_list = guest_session.get_data_disk()[1:]

    bs_size_list = ['8k', '16k', '32k', '64k', '128k', '256k', '4M', '1G']

    map(lambda dev, size:
        guest_session.guest_cmd_output(
            cmd='dd if=/dev/zero of=%s bs=%s count=1000 oflag=direct &'
                % (dev, size), timeout=600), data_disk_list, bs_size_list)
    while 1:
        if not guest_session.guest_cmd_output('pgrep -x dd'):
            break
        time.sleep(5)

    map(lambda dev, size:
        guest_session.guest_cmd_output(
            cmd='dd if=%s of=/dev/null bs=%s count=1000 iflag=direct &'
                % (dev, size), timeout=600), data_disk_list, bs_size_list)
    while 1:
        if not guest_session.guest_cmd_output('pgrep -x dd'):
            break
        time.sleep(5)

    guest_session.guest_dmesg_check()