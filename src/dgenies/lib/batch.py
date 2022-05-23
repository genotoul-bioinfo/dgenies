from dgenies.tools import Tools

JOB_TYPES = ["align", "plot"]


def has_correct_argument_keys(job_type: str, job_params: dict):
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
        optional = {"options", "query"}
        # if result of comparison of given params with expected params is not a subset of optional params,
        # then there is some unconsidered params in given params
        return comparison.issubset(optional)
    elif job_type == "plot":
        return job_params.keys() == {"target", "query", "align"} or job_params.keys() == {"backup"}
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
                if type in JOB_TYPES:
                    for p in params[1:]:
                        ps = p.split("=", 1)
                        if len(ps) > 1:
                            param_dict[ps[0].strip()] = ps[1].strip()
                        else:
                            error_msg.append("Malformated parameter on line {:d}: key=value format expected".format(i+1))
                    if has_correct_argument_keys(type, param_dict):
                        # We get the default options
                        tool = None
                        default_options = set()
                        if "tool" in param_dict:
                            try:
                                tool = tools[param_dict["tool"]]
                                default_options = tool.get_default_options_keys()
                            except KeyError:
                                error_msg.append("Tool {} do not exists on line {:d}".format(param_dict["tool"], i+1))
                                tool = None
                        # If options exists in job line, we split options value into a list of options
                        if "options" in param_dict:
                            if tool:
                                # TODO: manage exclusive options
                                # We transform option value ids (e.g. 0-0) into option strings
                                user_options_keys = set(param_dict["options"].split(","))
                                # We get the options to remove and the ones to effectively add
                                options_keys_to_remove = [o[1:] for o in user_options_keys if o.startswith("!")]
                                options_keys_to_add = [o for o in user_options_keys if not o.startswith("!")]
                                # We override the default options with the given ones
                                options = default_options.difference(options_keys_to_remove)
                                options.update(options_keys_to_add)
                                valid, param_list = tool.resolve_options_keys(options)
                                param_dict["options"] = " ".join(param_list)
                        # We add the job
                        job_param_list.append((type, param_dict))
                    else:
                        error_msg.append("Incorrect/missing argument key on line {:d}".format(i+1))
                else:
                    error_msg.append("Unknown job type on line {:d}".format(i + 1))
    return job_param_list, "; ".join(error_msg)
