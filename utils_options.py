import getopt
import sys
import os
import re
import yaml
from usr_exceptions import Error

BASE_FILE = os.path.dirname(os.path.abspath(__file__))

options_list = [
    "help",
    "show_category",
    "show_requirement=",
    "test_requirement=",
    "test_cases=",
    "verbose=",
    "repeat_times=",
    "src_host_ip=",
    "dst_host_ip=",
    "image_format=",
    "drive_format=",
    "share_images_dir=",
    "local_images_dir=",
    "sys_image_name=",
    "nfs_pek_ip=",
    "nfs_bos_ip="
]

help_info = "Usage: \n" \
            "python Start2Run.py --test_requirement=$requirement_id " \
            "[option] ... \n" \
            "Standard option: \n" \
            "--help         Display mouse tool help. \n" \
            "--show_requirement=$requirement id     \n" \
            "               Display all cases of requirement. \n" \
            "--test_requirement=$requirement id     \n" \
            "               Run all cases of requirement. \n" \
            "--test_cases=$case id0,$case id1,...   \n" \
            "               Run specific cases. \n" \
            "--verbose=yes|no \n" \
            "               Display the log of running. \n" \
            "--repeat_times=$times \n" \
            "               Run given cases with $times. \n" \
            "--src_host_ip=$ip addr \n" \
            "               Run given host for case. \n" \
            "--dst_host_ip=$ip addr \n" \
            "               Run given destination host for case. \n" \
            "--image_format=qcow2|raw \n" \
            "               Run given image format for case. \n" \
            "--drive_format=virtio-scsi|virtio-blk \n" \
            "               Run given drive format for case. \n" \
            "--share_images_dir=$images dir \n" \
            "               Run given share images directory for migration case. \n" \
            "--local_images_dir=$images dir \n" \
            "               Run given images directory for case. \n" \
            "--sys_image_name=$image name \n" \
            "               Run given system images for local host case. \n" \
            "--nfs_pek_ip=$nfs server pek ip \n" \
            "               Run given nfs server pek ip for case. \n" \
            "--nfs_bos_ip=$nfs server bos ip \n" \
            "               Run given nfs server bos ip for case. \n" \
            "Please see README for more information."

class Options(object):
    def __init__(self):
        self.options = self.initial_options()

    def show_requirement_info(self, id):
        file_path = ''
        search_name = id + '.yaml'
        index = 1
        for (thisdir, subshere, fileshere) in os.walk(BASE_FILE):
            for fname in fileshere:
                path = os.path.join(thisdir, fname)
                last_file = re.split(r'/', path)[-1]
                if search_name == last_file:
                    file_path = path
                    with open(file_path) as f:
                        params_dict = yaml.load(f)
                    print ("Category of requirement %s %s:"
                           % (id.upper().replace("_", "-"),
                              params_dict.get('test_requirement')['name']))
                    for case, info in params_dict['test_cases'].items():
                        print ("(%d) %s: %s" % (index,
                                                case.upper().replace("_", "-"),
                                                info['name']))
                        index = index + 1

        if not file_path:
            info = 'No found corresponding yaml file : %s' % search_name
            print (info)
            sys.exit(1)

    def usage(self):
        print ("%s" % help_info)

    def has_key(self, key):
        # Python 2 and 3
        return  key in self.options

    def initial_options(self):
        opt_dict = {}
        try:
            for args in sys.argv[1:]:
                if not re.findall(r'--', args):
                    print("Please Check the command again.")
                    self.usage()
                    sys.exit(1)
            options, args = getopt.getopt(sys.argv[1:], "", options_list)
            for opt, val in options:
                if opt == "--help":
                    self.usage()
                    sys.exit(1)
                elif opt == "--show_requirement":
                    if val:
                        self.show_requirement_info(val)
                        sys.exit(1)
                elif opt == "--test_requirement":
                    opt_dict[opt] = val
                elif opt == "--test_cases":
                    opt_dict[opt] = val
                elif opt == "--verbose":
                    opt_dict[opt] = val
                elif opt == "--repeat_times":
                    opt_dict[opt] = val
                elif opt == "--src_host_ip":
                    opt_dict[opt] = val
                elif opt == "--dst_host_ip":
                    opt_dict[opt] = val
                elif opt == "--image_format":
                    opt_dict[opt] = val
                elif opt == "--drive_format":
                    opt_dict[opt] = val
                elif opt == "--share_images_dir":
                    opt_dict[opt] = val
                elif opt == "--local_images_dir":
                    opt_dict[opt] = val
                elif opt == "--sys_image_name":
                    opt_dict[opt] = val
                elif opt == "--nfs_pek_ip":
                    opt_dict[opt] = val
                elif opt == "--nfs_bos_ip":
                    opt_dict[opt] = val

        except getopt.GetoptError:
            print("Please Check the command again.")
            self.usage()
            sys.exit(1)
        return opt_dict

    def set_pramas(self, params):
        for k, v in self.options.items():
            if k == '--verbose':
                params.get('verbose', v)
            if k == '--repeat_times':
                params.get('repeat_times', v)
            if k == '--src_host_ip':
                params.get('src_host_ip', v)
            if k == '--dst_host_ip':
                params.get('dst_host_ip', v)
            if k == '--image_format':
                params.get('image_format', v)
            if k == '--drive_format':
                params.get('drive_format', v)
            if k == '--share_images_dir':
                params.get('share_images_dir', v)
            if k == '--local_images_dir':
                params.get('local_images_dir', v)
            if k == '--sys_image_name':
                params.get('sys_image_name', v)
            if k == '--nfs_pek_ip':
                params.get('nfs_pek_ip', v)
            if k == '--nfs_bos_ip':
                params.get('nfs_bos_ip', v)

