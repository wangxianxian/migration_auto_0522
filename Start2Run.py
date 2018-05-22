import sys
import utils_params
import runner
import utils_log
from utils_options import Options

if __name__ == "__main__":
    test_modules = {}
    requirement_id = ''
    case_list = []

    options = Options()
    if options.has_key('--test_requirement') \
            and options.options['--test_requirement']:
        requirement_id = options.options['--test_requirement']
    else:
        print("Please Check the command again.")
        options.usage()
        sys.exit(1)
    if options.has_key('--test_cases') and options.options['--test_cases']:
        case_list = options.options['--test_cases'].split(",")

    params = utils_params.Params(requirement_id, case_list)

    log_dir = utils_log.create_log_file(requirement_id)
    params.get('log_dir', log_dir)

    options.set_pramas(params)
    params.convert_variables()

    runner = runner.CaseRunner(params)
    runner.main_run()