import time

def wait_for_output(func, timeout, first=0.0, step=1.0, text=None):

    start_time = time.time()
    end_time = time.time() + float(timeout)

    time.sleep(first)

    while time.time() < end_time:
        # if text:
        #     logging.debug("%s (%f secs)", text, (time.time() - start_time))

        output = func()
        if output:
            return output

        time.sleep(step)

    return None