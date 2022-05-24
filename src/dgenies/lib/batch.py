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
                no_error = True
                params = params_line.split()
                type = params[0]
                param_dict = {}
                if type in JOB_TYPES:
                    for p in params[1:]:
                        ps = p.split("=", 1)
                        if len(ps) > 1:
                            param_dict[ps[0].strip()] = ps[1].strip()
                        else:
                            error_msg.append("Line {:d}: Malformed parameter - key=value format expected".format(i+1))
                    if has_correct_argument_keys(type, param_dict):
                        # We get the default options
                        tool = None
                        default_options = set()
                        if "tool" in param_dict:
                            try:
                                tool = tools[param_dict["tool"]]
                                default_options = tool.get_default_option_keys()
                            except KeyError:
                                no_error = False
                                error_msg.append("Line {:d}: Tool {} does not exist".format(i+1, param_dict["tool"]))
                                tool = None
                        # If options exists in job line, we split options value into a list of options
                        if "options" in param_dict:
                            if tool:
                                # TODO: manage exclusive options
                                # We transform the user 'options' string into an option key list (e.g. 0-0)
                                user_option_keys = set(param_dict["options"].split(","))
                                # We check that user option keys are valid
                                invalid_keys = []
                                for k in user_option_keys:
                                    valid_key = tool.is_valid_option_key(k[1:]) if k.startswith("!") else tool.is_valid_option_key(k)
                                    if not valid_key:
                                        invalid_keys.append(k)
                                if not invalid_keys:
                                    # We get the options to remove and the ones to effectively add
                                    option_keys_to_remove = [k[1:] for k in user_option_keys if k.startswith("!")]
                                    option_keys_to_add = [k for k in user_option_keys if not k.startswith("!")]
                                    # We override the default options with the given ones
                                    exclusive_to_remove = set()
                                    for k in option_keys_to_add:
                                        if tool.is_an_exclusive_option_key(k):
                                            exclusive_to_remove.update(tool.get_option_keys(k))
                                    option_keys = default_options.difference(exclusive_to_remove).difference(option_keys_to_remove)
                                    option_keys.update(option_keys_to_add)
                                    # We check if it remains incompatible (exclusive) options in user options
                                    # by counting chosen options per exclusive groups. Count must be at most 1.
                                    groups = [tool.get_option_group(k) for k in option_keys]
                                    count_exclusives = {}
                                    for g in groups:
                                        count_exclusives[g] = count_exclusives.get(g, 0) + 1
                                    exclusive_violation = any((v > 1 for v in count_exclusives.values()))
                                    if not exclusive_violation:
                                        valid, option_list = tool.resolve_option_keys(option_keys)
                                        # We manage the fact that no option can exist when using '!'
                                        param_dict["options"] = " ".join(option_list) if option_list else None
                                    else:
                                        no_error = False
                                        error_msg.append("Line {:d}: Exclusive options were used together".format(i + 1, ",".join(invalid_keys)))
                                else:
                                    no_error = False
                                    error_msg.append("Line {:d}: Option key(s) {} is/are invalid".format(i + 1, ",".join(invalid_keys)))
                    else:
                        no_error = False
                        error_msg.append("Line {:d}: Incorrect/missing argument key".format(i+1))
                else:
                    no_error = False
                    error_msg.append("Line {:d}: Unknown job type".format(i + 1))
                if no_error:
                    # We add the job
                    job_param_list.append((type, param_dict))
    return job_param_list, "; ".join(error_msg)
