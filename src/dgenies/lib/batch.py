from dgenies.tools import Tools


def has_correct_arguments(job_type: str, job_params: dict):
    """
    Check if the parameters given for a job has correct argument keys
    :param job_type: file path
    :type job_type: str
    :param job_params: file path
    :type job_params: dict
    :return: True if the job_params match what is expected for the given job_type
    :rtype: bool
    """
    if job_type == "align":
        comparison = {"target", "query", "tool", "options"}.symmetric_difference(job_params.keys())
        return not comparison or comparison == {"options"}
    elif job_type == "plot":
        return job_params.keys() == {"target", "query", "map"} or job_params.keys() == {"backup"}
    return False


def read_batch_file(batch_file: str):
    """
    Check if the parameters given for a job has correct argument keys
    :param batch_file: file path
    :type batch_file: str
    :return: Couple of lists.
        * [0] a list of job parameters which will be used to determine job type
        * [1] a list of error messages for client feedback
    :rtype: tuple
    """
    job_param_list = []
    error_msg = []
    tools = Tools().tools
    with open(batch_file, 'rt') as instream:
        for i, line in enumerate(instream.readlines()):
            params_line = line.strip()
            # We do not consider blank lines and comment lines
            if params_line and not params_line.startswith("#"):
                params = params_line.split()
                type = params[0]
                param_dict = {}
                if type in ("align", "plot"):
                    for p in params[1:]:
                        ps = p.split("=")
                        if len(ps) > 1:
                            param_dict[ps[0].strip()] = "=".join(ps[1:]).strip()
                        else:
                            error_msg.append("Malformated parameter on line {:d}: key=value format expected".format(i))
                            pass
                else:
                    error_msg.append("Unkown job type on line {:d}".format(i))
                    pass
                if has_correct_arguments(type, param_dict):
                    # if exists we split options value into a list of options
                    # TODO: check tool key in Tools
                    if "options" in param_dict:
                        tool = tools[param_dict["tool"]]
                    # We transform option value ids (e.g. 0-0) into option strings
                        valid, param_list = tool.resolve_options_keys(param_dict["options"].split())
                        param_dict["options"] = " ".join(param_list)
                    # We add the job
                    job_param_list.append((type, param_dict))
                else:
                    error_msg.append("Incorrect/missing argument key on line {:d}".format(i))
    return job_param_list, error_msg