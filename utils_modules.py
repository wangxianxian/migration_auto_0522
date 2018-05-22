import os
import sys
import imp
import utils_params

BASE_FILE = os.path.dirname(os.path.abspath(__file__))

def init_modules():
    params = utils_params.Params('utils_modules')
    modules_file = params.get('test_scenarios')
    for file in modules_file:
        common_dir = os.path.abspath(
            os.path.join(BASE_FILE, file))
        sys.path.extend([common_dir])

def setup_modules(require_id):
    init_modules()
    params = utils_params.Params(require_id)
    params.build_dict_from_yaml()

    test_modules = {}
    for t_type in params.get('test_cases'):
        # Load the test module
        f, p, d = imp.find_module(t_type)
        test_modules[t_type] = imp.load_module(t_type, f, p, d)
        f.close()
    return test_modules

