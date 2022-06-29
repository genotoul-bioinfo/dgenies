from dgenies.tools import Tools
from dgenies.config_reader import AppConfigReader

JOB_TYPES = ["align", "plot"]
config = AppConfigReader()


def has_correct_argument_keys(job_type: str, job_params: dict):
    """
    Check if the parameters given for a job has correct argument keys
    :param job_type: file path
    :type job_type: str
    :param job_params: file path
    :type job_params: dict
    :return: a couple such as
        * [0] True if the job_params match what is expected for the given job_type
        * [1] The problematic keys
    :rtype: tuple
    """
    result = False, None
    if job_type == "align":
        comparison = {"target", "query", "tool", "options"}.symmetric_difference(job_params.keys())
        optional = {"options", "query", "tool", "job_id_prefix"}
        # if result of comparison of given params with expected params is not a subset of optional params,
        # then there is some unconsidered params in given params
        result = comparison.issubset(optional), comparison - optional
    elif job_type == "plot":
        #if ({"target", "query", "align"}.issubset(job_params.keys()) and "backup" not in job_params.keys()) \
        #        or ("backup" in job_params.keys() and not job_params.keys().issubset({"target", "query", "align"})):
        #    comparison = job_params.keys().difference({"target", "query", "align", "backup"})
        # plot job must contain keys ("target", "query", "align") xor ("backup")
        if "backup" in job_params.keys():
            comparison = {"backup"}.symmetric_difference(job_params.keys())
        else:
            comparison = {"target", "query", "align"}.symmetric_difference(job_params.keys())
        optional = {"job_id_prefix"}
        result = comparison.issubset(optional), comparison - optional
    return result


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
    tools = Tools()
    with open(batch_file, 'rt') as instream:
        nb_lines = 0
        for i, line in enumerate(instream.readlines()):
            params_line = line.strip()
            # We do not consider blank lines and comment lines
            if params_line and not params_line.startswith("#"):
                nb_lines += 1
                if nb_lines > config.max_nb_jobs_in_batch_mode:
                    break
                no_error = True
                params = params_line.split()
                param_dict = {}
                type = None
                for p in params:
                    ps = p.split("=", 1)
                    if len(ps) > 1:
                        param_dict[ps[0].strip()] = ps[1].strip()
                    else:
                        error_msg.append("Line {:d}: Malformed parameter '{}', key=value format expected".format(i + 1, p))
                if "type" in param_dict:
                    type = param_dict.pop("type")
                    if type in JOB_TYPES:
                        is_correct, prob_keys = has_correct_argument_keys(type, param_dict)  # We get the default options
                        if is_correct:
                            toolname = tools.get_default()
                            default_options = set()
                            if "tool" in param_dict:
                                toolname = param_dict["tool"]
                            else:
                                param_dict["tool"] = toolname
                            try:
                                tool = tools.tools[toolname]
                                default_options = tool.get_default_option_keys()
                            except KeyError:
                                no_error = False
                                error_msg.append("Line {:d}: Tool {} does not exist".format(i+1, toolname))
                                tool = None
                            # If options exists in job line, we split options value into a list of options
                            if tool:
                                if "options" in param_dict:
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
                                    valid, option_list = tool.resolve_option_keys(default_options)
                                    param_dict["options"] = " ".join(option_list) if option_list else None
                        else:
                            no_error = False
                            error_msg.append("Line {:d}: Incorrect/missing argument key: {}".format(i+1, prob_keys))
                    else:
                        no_error = False
                        error_msg.append("Line {:d}: Unknown job type".format(i + 1))
                else:
                    error_msg.append("Missing mandatory key: 'type'".format(i + 1))
                if no_error:
                    # We add the job
                    job_param_list.append((type, param_dict))
    return job_param_list, "; ".join(error_msg)
