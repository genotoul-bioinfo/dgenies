if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.run = {};

// We change tmpl.regexp to [% syntax instead of {% in order to avoid conflit with jinja2 templates
tmpl.regexp = /([\s'\\])(?!(?:[^[]|\[(?!%))*%\])|(?:\[%(=|#)([\s\S]+?)%\])|(\[%)|(%\])/g

// Init global variables:
dgenies.run.s_id = null;
dgenies.run.allowed_ext = [];
dgenies.run.max_upload_file_size = -1
dgenies.run.files = [undefined, undefined, undefined, undefined, undefined, undefined, undefined];
dgenies.run.files_nb = {
    "query": 0,
    "target": 1,
    "queryidx": 2,
    "targetidx": 3,
    "alignfile": 4,
    "backup": 5,
    "batch" : 6
};
dgenies.run.allow_upload = false;
dgenies.run.ping_interval = null;
dgenies.run.target_example = "";
dgenies.run.query_example = "";
dgenies.run.backup_example = "";
dgenies.run.batch_example = "";
dgenies.run.tools = [];
dgenies.run.tool_has_ava = {};
dgenies.run.tools_checking = {};
dgenies.run.tools_options = {}
dgenies.run.max_jobs = 1
dgenies.run.enabled = true;
dgenies.run.valid = true;

dgenies.run.FTYPES = {
    "query": {"formats": ["fasta",]},
    "target": {"formats": ["fasta",]},
    "queryidx": {"formats": ["fasta", "idx"]},
    "targetidx": {"formats": ["fasta", "idx"]},
    "alignfile": {"formats": ["map"]},
    "backup": {"formats": ["backup"]},
    "batch": {"formats": ["batch"]},
}

dgenies.run.FTYPES_REGEX = {
    "fasta": /^.+\.(fa|fna|fasta)(\.gz)?$/,
    "idx": /^.+\.idx(\.gz)?$/,
    "map": /^.+\.paf$/,
    "backup": /^.+\.tar(\.gz)?$/,
    "batch": /^.+\.(tab|tsv|txt)$/,
}


// Keys in batch file that will use files
dgenies.run.KEYS_FOR_FILES = ["alignfile", "backup", "query", "target", "queryidx", "targetidx"]
//dgenies.run.FILE_STATES = ["available", "duplicated", "missing", "unused"]

// list of files in batch file: array of strings
dgenies.run.files_in_batch = new Array()
// list of to be uploaded files: array of fileupload objects
dgenies.run.files_for_batch = new Array()
// states for files: dict of str: array of strings
dgenies.run.file_states = []
dgenies.run.missing_files = []
// Job list that will be send to server
dgenies.run.job_list = []
dgenies.run.batch_errors = []

// list of fileupload that will be uploaded
dgenies.run.files_to_upload = []
dgenies.run.editor = null;


/**
 * Initialise app for run page
 *
 * @param {string} s_id session id
 * @param {object} allowed_ext
 * @param {int} max_upload_file_size maximum upload file size
 * @param {string} target_example target example pseudo path
 * @param {string} query_example query example pseudo path
 * @param {string} backup_example backup example pseudo path
 * @param {string} batch_example batch example pseudo path
 * @param {object} tool_has_ava defines if each available tool has an all-vs-all mode
 * @param {object} tools_checking options for each tool
 * @param {int} max_jobs maximum number of jobs in batch file
 */
dgenies.run.init = function(s_id, allowed_ext, max_upload_file_size=1073741824, target_example="", query_example="",
                            backup_example="", batch_example="", tools=[], tool_has_ava={}, tools_checking={}, max_jobs = 1) {
    dgenies.run.s_id = s_id;
    dgenies.run.allowed_ext = allowed_ext;
    dgenies.run.max_upload_file_size = max_upload_file_size;
    dgenies.run.target_example = target_example;
    dgenies.run.query_example = query_example;
    dgenies.run.batch_example = batch_example;
    dgenies.run.backup_example = backup_example;
    dgenies.run.tools = tools;
    dgenies.run.tool_has_ava = tool_has_ava;
    dgenies.run.tools_checking = tools_checking;
    dgenies.run.tools_options = {}
    for(let tool in dgenies.run.tools_checking){
        if(dgenies.run.tools_checking.hasOwnProperty(tool)) {
            let value = dgenies.run.tools_checking[tool]
            let data = {}
            for (let opt of value.options){
                for (let choice of opt.choices){
                    data[choice] = {
                        group: opt.group,
                        exclusive: opt.exclusive
                    }
                }
            }
            dgenies.run.tools_options[tool] = data
        }
    };
    dgenies.run.max_jobs = max_jobs
    dgenies.run.restore_form();
    dgenies.run.set_events();
    dgenies.run.init_fileuploads();
    dgenies.run.init_codemirror();
};


/**
 * Refresh everything related to files for batch job
 * @param {bool} relint Lint the batch file content (default = true)
 */
dgenies.run.refresh_files_status = function(relint = true){
    // We check the uploaded files and the files in batch
    dgenies.run.check_files();
    // We refresh the file listing
    dgenies.run.refresh_html_listing();
    // We relint the batch content
    if (relint){
        dgenies.run.relint();
    }
}

/**
 * Remove some files from listing
 * @param {*} jq_selection Element selection from jquery
 */
dgenies.run.jq_remove_from_listing = function(jq_selection) {
    // We get selection index
    let selection_idx = Array.from(jq_selection, e => $(e).data("index"))
    // We update the list of file
    let new_file_list = new Array()
    for (let i = 0; i < dgenies.run.files_for_batch.length; i++){
        if (! selection_idx.includes(i)){
            new_file_list.push(dgenies.run.files_for_batch[i])
        }
    }
    dgenies.run.files_for_batch = new_file_list
    dgenies.run.refresh_files_status()
}

/**
 * Regenerate the html file listing
 */
dgenies.run.refresh_html_listing = function() {
    
    let list = []
    for (let i=0; i<dgenies.run.files_for_batch.length; i++){
        let data = {
            "name": dgenies.run.files_for_batch[i].files[0].name,
            "size": dgenies.run.files_for_batch[i].files[0].size,
            "state": dgenies.run.file_states[i],
        }
        list.push(data)
    }
    
    // We update the html part
    $('#listing').find('tbody:first').html(tmpl('tmpl-listing', list))
            // We reset the delete button events
            $(":button[id^='delete-btn']").click(function() {
                let i = $(this).parents("tr").data("index")
                dgenies.run.files_for_batch.splice(i, 1)
                dgenies.run.refresh_files_status()
            })
}

/**
 * Check the state of uploaded files
 *
 * @param {array} needed_files list of filenames from batch file needed to upload
 * @param {array} uploaded_files list of filenames in upload field
 * @returns {array} a list of string with the same length than @uploaded_files
 **/
dgenies.run.check_uploaded_files = function(needed_files, uploaded_files){
    // list of states (following the order of list of files)
    let states = []

    // We count filename occurences
    let count = new Map();
    for (let f of uploaded_files.flat()) {
        if (count.has(f)) {
            count.set(f, count.get(f) + 1)
        } else {
            count.set(f, 1);
        }
    }

    // We only check duplication for available files
    for (let f of uploaded_files.flat()){
        if (needed_files.includes(f)){
            if (count.get(f) > 1) {
                states.push("duplicated")
            } else {
                states.push("available")
            }
        } else {
            states.push("unused")
        }
    }
    return states
}



/**
 * Get the list of uploaded files
 *
 * @returns {array} a list of string
 **/
dgenies.run.get_uploaded_files = function(){
    return Array.from(dgenies.run.files_for_batch, function(elem){return elem.files[0].name})
}



/**
 * Check which files are missing in batch files
 *
 * @param {array} needed_files list of filenames from batch file needed to upload
 * @param {array} uploaded_files list of filenames in upload field
 * @returns {array} a list of string with the same length than @uploaded_files
 **/
dgenies.run.check_missing_files = function(needed_files, uploaded_files){
    return needed_files.filter(
        function(x) { return uploaded_files.indexOf(x) < 0 }
    );
}

/**
 * Compute states of files, both for uploaded ones and missing ones
 **/
dgenies.run.check_files = function(){
    let uploaded_files = dgenies.run.get_uploaded_files()
    dgenies.run.file_states = dgenies.run.check_uploaded_files(dgenies.run.files_in_batch, uploaded_files)
    dgenies.run.missing_files = dgenies.run.check_missing_files(dgenies.run.files_in_batch, uploaded_files)
}

/**
 * Generate the list of filenames used in the list of jobs
 * @param {array} job_list list of jobs
 * @returns {array} a list of string
 **/
dgenies.run.get_local_files = function(job_list){
    let needed_files = new Set();
    for (let j of job_list){
        for (let k of dgenies.run.KEYS_FOR_FILES) {
            if (`${k}_type` in j && j[`${k}_type`] === "local") {
                needed_files.add(j[k])
            }
        }
    }
    return Array.from(needed_files);
};


/**
 * Check if file has the right extension.
 * 
 * @param {string} type the job type
 * @param {string} key the param key
 * @param {string} val the param value
 * @return a map if something wrong, undefined else
 */
dgenies.run.check_file_format_and_presence = function(type, key, val){
    let corrected_key = key
    if ((key == "query" || key == "target") && type == "plot") {
        corrected_key = key + "idx" 
    } else if (key == "align"){
        corrected_key = "alignfile" 
    }
    if (dgenies.run.KEYS_FOR_FILES.includes(corrected_key) && (! dgenies.run.check_url(val, false))) {
        if (val.startsWith("example://")){
            let example_url = ""
            if (`${key}_example` in dgenies.run){
                example_url = dgenies.run[`${key}_example`]
            }
            if (("example://" + example_url) != val){
                return {
                    message: example_url=="" ? `No example url for ${key}` : `Example link must be: "example://${example_url}"`,
                    severity: "error"
                }
            }
        } else {
            let regexps = dgenies.run.FTYPES[corrected_key].formats.map(function(x){return dgenies.run.FTYPES_REGEX[x]})
            let has_match = false;
            for (let e of regexps){
                has_match = has_match || e.test(val)
            }
            if (! has_match){
                return {
                    message: `File must be have the following format for ${key}: ${dgenies.run.FTYPES[corrected_key].formats.join(", ")}`,
                    severity: "error"
                }
            } else {
                let uploaded_files = dgenies.run.get_uploaded_files();
                if(! uploaded_files.includes(val)){
                    return {
                        message : `Missing file in user files: ${val}`,
                        severity: "warning"
                    }
                }
        }
        }
    }
    return undefined
}


/**
 * Check if file has the right extension.
 * 
 * @param {*} job list of params
 * @param {*} param_dict dict associating key to params
 * @param {*} param_dict first token apparing in job string
 * @param {*} param_dict last token apparing in job string
 * @return list of found errors and warnings
 */
dgenies.run.ckeck_align_job = function(job, param_dict, start_token, end_token) {
    let found = []
    // check tool
    let has_ava = true
    if (!("tool" in param_dict)){

        found.push({
            "message": `Missing key "tool"`,
            "severity": "error",
            "from": CodeMirror.Pos(start_token.startLine - 1, start_token.startColumn-1),
            "to": CodeMirror.Pos(end_token.endLine - 1, end_token.endColumn)
        })
    } else {
        let tool_val = param_dict["tool"].val
        let tool = tool_val.image
        if (! dgenies.run.tools.includes(tool)){
            found.push({
                "message": `Tool "${tool}" is unknown, please use ones of following choice: ${dgenies.run.tools.join(", ")}`,
                "severity": "error",
                "from": CodeMirror.Pos(tool_val.startLine - 1, tool_val.startColumn-1),
                "to": CodeMirror.Pos(tool_val.endLine - 1, tool_val.endColumn)
            })
        } else {
            has_ava =  dgenies.run.tool_has_ava[tool] // for ava param checking
            let options = dgenies.run.tools_checking[tool].default
            let options_val = {
                image: options.join(","),
                startLine : start_token.startLine,
                startColumn: start_token.startColumn,
                endLine : start_token.endLine,
                endColumn: start_token.endColumn
            }
            // Manage options
            if ("options" in param_dict){
                options_val = param_dict["options"].val
                options = options_val.image.split(",")
            } else {
                found.push({
                    "message": `Missing key "options", will use "options=${options.join(",")}"`,
                    "severity": "warning",
                    "from": CodeMirror.Pos(start_token.startLine - 1, start_token.startColumn-1),
                    "to": CodeMirror.Pos(end_token.endLine - 1, end_token.endColumn)
                })
            }
            let allowed_options = Object.keys(dgenies.run.tools_options[tool])
            let unknown_options = options.filter(function(opt) {
                return ! allowed_options.includes(opt);
            });
            // TODO: manage option exclusion
            if (unknown_options.length > 0) {
                found.push({
                    "message": `unknown option "${unknown_options.join(", ")}", please use options in following list: ${allowed_options.join(", ")}`,
                    "severity": "error",
                    "from": CodeMirror.Pos(options_val.startLine - 1, options_val.startColumn-1),
                    "to": CodeMirror.Pos(options_val.endLine - 1, options_val.endColumn)
                });
            } else {
                // Manage option exclusion
                let exclusive = {}
                for (let opt of options) {
                    let k = dgenies.run.tools_options[tool][opt]
                    if (k.exclusive && k.group in exclusive){
                        exclusive[k.group].push(opt)
                    } else {
                        exclusive[k.group] = [opt]
                    }
                }
                for (let g of Object.keys(exclusive)){
                    if (exclusive[g].length > 1){
                        found.push({
                            "message": `Incompatible options: ${exclusive[g].join(", ")}`,
                            "severity": "error",
                            "from": CodeMirror.Pos(options_val.startLine - 1, options_val.startColumn-1),
                            "to": CodeMirror.Pos(options_val.endLine - 1, options_val.endColumn)
                        });
                    }
                }
            }
        }
    }

    // check mandatory and optional params (appart 'type' and 'tool')
    let mandatory = ["target", "type", "tool"]
    let optional = ["id_job", "options"]

    if (has_ava){
        mandatory.push("query")
    } else {
        optional.push("query")
    }

    let all_allowed = mandatory.concat(optional)
    for (let param of job){
        let key = param[0];
        if (!all_allowed.includes(key.image)){
            found.push({
                "message": `Unknown key "${key.image}"`,
                "severity": "error",
                "from": CodeMirror.Pos(key.startLine - 1, key.startColumn-1),
                "to": CodeMirror.Pos(key.endLine - 1, key.endColumn)
            })
        }
    }
    return found
}


/**
 * Check if file has the right extension.
 * 
 * @param {*} job list of params
 * @param {*} param_dict dict associating key to params
 * @param {*} param_dict first token apparing in job string
 * @param {*} param_dict last token apparing in job string
 * @return list of found errors and warnings
 */
dgenies.run.ckeck_plot_job = function(job, param_dict, start_token, end_token) {
    let found = []
    // check either backup file or individual files
    if (("align" in param_dict) || ("query" in param_dict) || ("target" in param_dict)){
        if ("backup" in param_dict){
            let backup_key = param_dict["backup"].key
            found.push({
                "message": '"backup" key is exclusive with "align", "query" and "target" keys',
                "severity": "error",
                "from": CodeMirror.Pos(backup_key.startLine - 1, backup_key.startColumn-1),
                "to": CodeMirror.Pos(backup_key.endLine - 1, backup_key.endColumn)
            });
            for (let p of ["align", "query", "target"]) {
                let key = param_dict[p].key
                if (key !== undefined){
                    found.push({
                        "message": `"${key.image}" key cannot be used with "backup" key`,
                        "severity": "error",
                        "from": CodeMirror.Pos(key.startLine - 1, key.startColumn-1),
                        "to": CodeMirror.Pos(key.endLine - 1, key.endColumn)
                    });
                }
            }
        } else {
            // check for missing individual files
            for (let p of ["align", "query", "target"]) {
                if (param_dict[p] === undefined){
                    found.push({
                        "message": `Missing ${p} key`,
                        "severity": "error",
                        "from": CodeMirror.Pos(start_token.startLine - 1, start_token.startColumn-1),
                        "to": CodeMirror.Pos(end_token.endLine - 1, end_token.endColumn)
                    })
                }
            }
        }
    } else if (!("backup" in param_dict)){
        found.push({
            "message": `Missing either "backup" key or "align", "query" and "target" keys`,
            "severity": "error",
            "from": CodeMirror.Pos(start_token.startLine - 1, start_token.startColumn-1),
            "to": CodeMirror.Pos(end_token.endLine - 1, end_token.endColumn)
        })
    }

    // check for mandatory and optional keys
    let mandatory = [["align", "type", "query", "target"], ["type", "backup"]]
    let optional = ["id_job"]
    let all_allowed = mandatory.map(function(x){return x.concat(optional)})
    let present_keys = job.map(function(param){return param[0];})
    let unknown_keys = present_keys.filter(
        function(k){
            return all_allowed.every(
                function(x){
                    return !x.includes(k.image)
                });
            });
    for (let key of unknown_keys){
        found.push({
            "message": `Unknown key "${key.image}"`,
            "severity": "error",
            "from": CodeMirror.Pos(key.startLine - 1, key.startColumn-1),
            "to": CodeMirror.Pos(key.endLine - 1, key.endColumn)
        });
    }
    return found
}



/**
 * Check if file has the right extension.
 * 
 * @param {job} type the job
 * @return list of found errors and warnings
 */
dgenies.run.ckeck_job = function(job) {
    let found = []
    let param_dict = {}
    let jobtype;
    let start_token = job[0][0]
    let end_token = job[job.length-1][1]

    // looking for duplicated keys
    for (let param of job){
        let [key, val] = param
        if (key.image in param_dict){
            found.push({
                "message": `Duplicate key: ${key.image}`,
                "severity": "error",
                "from": CodeMirror.Pos(key.startLine - 1, key.startColumn-1),
                "to": CodeMirror.Pos(key.endLine - 1, key.endColumn)
            })
        }
        param_dict[key.image] = {key: key, val: val}
    }
    // get job type
    if ("type" in param_dict) {
        let param_val = param_dict["type"].val
        jobtype = param_val.image
        if (! ["align", "plot"].includes(jobtype)){
            found.push({
                "message": `Unknown type: ${jobtype}`,
                "severity": "error",
                "from": CodeMirror.Pos(param_val.startLine - 1, param_val.startColumn-1),
                "to": CodeMirror.Pos(param_val.endLine - 1, param_val.endColumn)
            })
        }
    } else {
        found.push({
            "message": `Missing mandatory key: type`,
            "severity": "error",
            "from": CodeMirror.Pos(start_token.startLine - 1, start_token.startColumn-1),
            "to": CodeMirror.Pos(end_token.endLine - 1, end_token.endColumn)
        })
    }
    // manage align job parameters
    if (jobtype == "align"){
        found = found.concat(dgenies.run.ckeck_align_job(job, param_dict, start_token, end_token))
    } else {
        // jobtype == "plot"
        found = found.concat(dgenies.run.ckeck_plot_job(job, param_dict, start_token, end_token))
    }

    // check file format and missing files
    for (let param of job){
        let [key, val] = param
        let error = dgenies.run.check_file_format_and_presence(jobtype, key.image, val.image)
        if (error !== undefined){
            found.push({
                "message": error.message,
                "severity": error.severity,
                "from": CodeMirror.Pos(val.startLine - 1, val.startColumn-1),
                "to": CodeMirror.Pos(val.endLine - 1, val.endColumn)
            })
        }
    }
    return found
}


/**
 * Adjust and complete each job parameters after parsing batch file.
 * 
 * @param {string} jobs the job list
 */
dgenies.run.adjust_job_list = function(jobs){
    for (let job of jobs){
        // rename 'align' key to 'alignfile'
        if ("align" in job){
            job["alignfile"] = job["align"]
            delete job["align"];
        }
        // add the file type (url or local)
        for (let k of dgenies.run.KEYS_FOR_FILES){
            if (`${k}` in job){
                if(dgenies.run.check_url(job[`${k}`])){
                    job[`${k}_type`] = "url"
                } else {
                    job[`${k}_type`] = "local"
                }
            }
        }
    }
}


/**
 * Create list of jobs from parse list of jobs
 * 
 * @param {string} jobs the job list
 * @returns {array} a list of dict
 */
dgenies.run.create_job_list = function(jobs){
    let job_list = []
    for (let j of jobs){
        let job = {}
        for (let param of j){
            let [key, val] = param
            job[key.image] = val.image
        }
        job_list.push(job)
    }
    dgenies.run.adjust_job_list(job_list)
    return job_list
}

/*
 * Relint batch editor by refreshing its content
 */
dgenies.run.relint = function() {
    CodeMirror.signal(dgenies.run.editor, "change", dgenies.run.editor)
    // Alt way...
    //dgenies.run.editor.setValue(dgenies.run.editor.getValue())
}


/**
 * Parse a batch file and add it in html
 **/
dgenies.run.read_batch = function() {
    console.log("Change batch file");
    const [f] = this.files;
    // TODO: check file type (mime = text)
    const reader = new FileReader();
    // resulting job list
    if (f) {

        reader.readAsText(f);

        reader.onload = function(e) {
            dgenies.run.editor.setValue(reader.result)
          };
        
        reader.onerror = function(e) {
            dgenies.notify(`Error while reading batch file: ${e.target.error}!`, "danger");
            console.log(e.target.error);
        };
    } else {
        dgenies.run.editor.setValue(reader.batch_default_content)
    }
  }


/**
 * Restore run form
 */
dgenies.run.restore_form = function () {
    let ftypes = ["query", "target", "queryidx", "targetidx", "alignfile", "backup", "batch"];
    for (let f in ftypes) {
        let ftype = ftypes[f];
        dgenies.run.change_fasta_type(ftype, $(`select.${ftype}`).find(":selected").text().toLowerCase(), true);
    }
};

/**
 * Upload next file
 *
 * @returns {boolean} true if there is a next upload, else false and run submit
 */
dgenies.run.upload_next = function () {
    let next = dgenies.run.files_to_upload.pop();
    while (next === undefined && dgenies.run.files_to_upload.length > 0) {
        next = dgenies.run.files_to_upload.pop();
    }
    if (next !== undefined) {
        next.submit();
        return true;
    }
    dgenies.run.do_submit();
    return false;
};

/**
 * Notify and reanable form on upload server error
 *
 * @param {string} fasta fasta file (name) which fails
 * @param data data from server call
 * @private
 */
dgenies.run.__upload_server_error = function(fasta, data) {
    dgenies.notify("message" in data ? data["message"]: `An error has occured when uploading <b>${fasta}</b> file. Please contact us to report the bug!`,
                    "danger");
    dgenies.run.enable_form();
};

/**
 * Check if a file has a valid format
 *
 * @param {string} filename filename
 * @param {array} formats expected file format
 * @returns {boolean} true if valid, else false
 */
dgenies.run.allowed_file = function (filename, formats) {
    let allowed_ext = [];
    for (let f in formats) {
        let format = formats[f];
        allowed_ext += dgenies.run.allowed_ext[format];
    }
    return filename.indexOf('.') !== -1 &&
        (allowed_ext.indexOf(filename.rsplit('.', 1)[1].toLowerCase()) !== -1 ||
         allowed_ext.indexOf(filename.rsplit('.', 2).splice(1).join(".").toLowerCase()) !== -1);
};

/**
 * Init file upload forms stuff
 *
 * @param {string} ftype type of file (query, target, ...)
 * @param {array} formats valid formats
 * @param {int} position position of file in the upload queue
 * @private
 */
dgenies.run._init_fileupload = function(ftype, formats, position) {
    $(`input.file-${ftype}`).fileupload({
        dataType: 'json',
        dropZone: $(`#dropzone-${ftype}`),
        formData: {
            "s_id": dgenies.run.s_id,
            "formats": formats
        },
        add: function (e, data) {
            let filename = data.files[0].name;
            if (dgenies.run.allowed_file(filename, formats))
                dgenies.run.files[position] = data;
            else {
                $(`input.file-${ftype}`).trigger("change"); // The value is null after fired
                dgenies.notify(`File <b>${filename}</b> is not supported!`, "danger", 3000)
            }
        },
        progressall: function (e, data) {
            let progress = parseInt(data.loaded / data.total * 100, 10);
            $(`#progress-${ftype}`).find('.bar').css(
                'width',
                progress + '%'
            );
        },
        success: function (data, success) {
            if (data["success"] !== "OK") {
                dgenies.run.__upload_server_error(ftype, data);
            }
            else if ("error" in data["files"][0]) {
                dgenies.run.add_error("Query file: " + data["files"][0]["error"], "error");
                dgenies.run.enable_form();
            }
            else {
                // get the rename file (if renamed) from the server side
                $(`input#${ftype}`).val(data["files"][0]["name"]);
                dgenies.run.hide_loading(ftype);
                dgenies.run.show_success(ftype);
                dgenies.run.upload_next();
            }
        },
        error: function (data, success) {
            dgenies.run.__upload_server_error(ftype, data);
        }
    });
};

dgenies.run._init_multiple_fileupload = function(formats) {
    // batch file upload
    $('#batch-multiple-files-upload').fileupload({
        dataType: 'json',
        formData: {
            "s_id": dgenies.run.s_id,
            "formats": formats
        },
        maxNumberOfFiles: 1, // max_files_for_a_job * number_of_jobs * 1.1 = 3 * 10 * 1.1
        dropZone: $('#input-dropzone'),
        add: function (e, data) {
            // We add the file
            dgenies.run.files_for_batch.push(data);
            // We refresh batch status
            dgenies.run.refresh_files_status()
        },
        drop: function (e, data) {
            $.each(data.files, function (index, file) {
                console.log('Dropped file: ' + file.name);
            });
        },
        change: function (e, data) {
            $.each(data.files, function (index, file) {
                console.log('Selected file: ' + file.name);
            });
        },
        done: function (e, data) {
            console.log('Upload finished.');
        },
        success: function (data, success) {
            console.log(data)
            if (data["success"] !== "OK") {
                dgenies.notify("message" in data ? data["message"]: `An error has occured when uploading multiple file. Please contact us to report the bug!`,
            "danger");
                dgenies.run.enable_form();
            }
            else if ("error" in data["files"][0]) {
                dgenies.run.add_error("Query file: " + data["files"][0]["error"], "error");
                dgenies.run.enable_form();
            }
            else {
                dgenies.run.upload_next();
            }
        },
        error: function (data, success) {
            dgenies.notify("message" in data ? data["message"]: `An error has occured when uploading multiple files. Please contact us to report the bug!`,
                    "danger");
            dgenies.run.enable_form();
        }
    });
};

/**
 * Init file upload forms
 */
dgenies.run.init_fileuploads = function () {
    let ftypes = dgenies.run.FTYPES;
    $.each(ftypes, function(ftype, data) {
        let formats = data["formats"];
        let position = dgenies.run.files_nb[ftype];
        dgenies.run._init_fileupload(ftype, formats, position);
        //Trigger events on hidden file inputs:
        $(`button#button-${ftype}`).click(function() {
            $(`input.file-${ftype}`).trigger("click");
        });
    });

    // We set add buton from multiple upload behavior
    dgenies.run._init_multiple_fileupload(["fasta", "idx", "map", "backup"]);
    $(":button[id='multiple-files-btn']").click(function() 
    {
        $("#batch-multiple-files-upload").trigger("click")
    })

    // We set behavior of 'remove unused' button
    $(":button[id='delete-unused-btn']").click(function() {
        dgenies.run.jq_remove_from_listing($('#listing').find('tr.unused-file'))
        dgenies.run.refresh_files_status()
    })

    // We set behavior of 'clear all' button
    $(":button[id='delete-all-btn']").click(function() {
        dgenies.run.files_for_batch = new Array()
        dgenies.run.refresh_files_status()
    })

    // We set bname behavior on change
    $("#bname").on("change", dgenies.run.read_batch);
    //dgenies.run.batch_text_interval = window.setInterval(dgenies.run.parse_if_batch_text_change, 1000);
};

dgenies.run.init_codemirror = function () {

    CodeMirror.defineSimpleMode("batch", {
        // The start state contains the rules that are initially used
        start: [
            {regex: /(?:type|align|query|target|backup|tool|options|id_job)\b/, token: "key"},
            {regex: /=/, token: "affectation", next: "value"},
        ],
        value: [
            {regex: /[^\s'"]+/, token: "value", next: "start"},
            {regex: /"[^"\r\n]+"/, token: "qvalue", next: "start"},
            {regex: /'[^'\r\n]+'/, token: "qvalue", next: "start"}
        ],
        meta: {
            dontIndentStates: ["start", "value"],
            lineComment: "//"
        }
    });

    CodeMirror.registerHelper("lint", "batch", function(text) {
        let res = dgenies.run.batchParser.parse(text);
        let found = res.lexErrors.map(
            (elem) => {return {
                "message": elem.message,
                "severity": "error",
                "from": CodeMirror.Pos(elem.line - 1, elem.column - 1),
                "to": CodeMirror.Pos(elem.line - 1, elem.column + elem.length)
            }}
        ).concat(res.parseErrors.map(
            (elem) => {return {
                "message": elem.message,
                "severity": "error",
                "from": CodeMirror.Pos(elem.token.startLine - 1, elem.token.startOffset),
                "to": CodeMirror.Pos(elem.token.endLine - 1, elem.token.startOffset + elem.token.image.length)
            }}
        ))

        // Additional checking
        // Limit number of jobs
        let jobs = res.data.slice(0,10)
        if (res.data.length > dgenies.run.max_jobs){
            dgenies.notify(`Batch file too long, only ${dgenies.run.max_jobs} first jobs were considered!`, "warning", 3000);
            let ignored_jobs = res.data.slice(dgenies.run.max_jobs)
            for (let j of ignored_jobs){
                let start = j[0][0]
                let end = j[j.length-1][1]
                found.push({
                    "message": `Only ${dgenies.run.max_jobs} first jobs are considered!`,
                    "severity": "warning",
                    "from": CodeMirror.Pos(start.startLine - 1, start.startColumn-1),
                    "to": CodeMirror.Pos(end.endLine - 1, end.endColumn)
                })
            }
        } 

        // check each job parameters
        for (let j of jobs){
            found = found.concat(dgenies.run.ckeck_job(j))
        }

        // convert to POST message
        dgenies.run.job_list = dgenies.run.create_job_list(jobs)
        // Get files to upload in jobs
        // TODO: remove get_local_files and get local file in dgenies.run.ckeck_job 
        dgenies.run.files_in_batch = dgenies.run.get_local_files(dgenies.run.job_list)
        dgenies.run.refresh_files_status(false)

        dgenies.run.batch_errors = found
        return found;
    });
    
    CodeMirror.defineMIME("text/plain", "batch");

    dgenies.run.editor = CodeMirror.fromTextArea(batch_content, {
        lineNumbers: true,
        mode: "batch",
        lineWrapping: true,
        theme: "dgenies",
        gutters: ["CodeMirror-lint-markers"],
        lint: true,
        selfContain: true
    });
}


/**
 * Get file size (human readable)
 *
 * @param {int} size file size in bytes
 * @returns {string} human readable size
 */
dgenies.run.get_file_size_str = function(size) {
    if (size < 1000) {
        return size + " O";
    }
    else if (size < 1000000) {
        return Math.round(size / 1024) + " Ko";
    }
    else if (size < 1000000000) {
        return Math.round(size / 1048576) + " Mo";
    }
    return Math.round(size / 1073741824) + " Go";
};

/**
 * Fill inputs with example data
 */
dgenies.run.fill_examples = function (tab) {
    dgenies.run.show_tab(tab);
    if (tab == "tab1") {
        $("select.target").val("1").trigger("change");
        $("input#target").val("example://" + dgenies.run.target_example);
        if (dgenies.run.query_example !== "") {
            $("select.query").val("1").trigger("change");
            $("input#query").val("example://" + dgenies.run.query_example);
        }
    }
    if (tab == "tab2") {
        $("select.backup").val("1").trigger("change");
        $("input#backup").val("example://" + dgenies.run.backup_example);
    }
    if (tab == "tab3") {
        $("select.batch").val("1").trigger("change");
        dgenies.get(
            "/example/batch",
            {},
            function (data) {
                $("#bname").val('');
                dgenies.run.editor.setValue(data);
            }
        )
        
    }
};

/**
 * Initialise file change events
 *
 * @param {string} ftype type of file (query, target, ...)
 * @private
 */
dgenies.run._set_file_event = function(ftype) {
    let max_file_size_txt = dgenies.run.get_file_size_str(dgenies.run.max_upload_file_size);
    $(`input.file-${ftype}`).change(function () {
        let file_size = $(`div.file-size.${ftype}`);
        if (this.files.length > 0)
            if (this.files[0].size <= dgenies.run.max_upload_file_size) {
                file_size.html(dgenies.run.get_file_size_str(this.files[0].size));
                dgenies.run.set_filename(this.files[0].name, ftype);
                if (["alignfile", "targetidx", "queryidx"].indexOf(ftype) > -1) {
                    dgenies.run.reset_file_input("backup");
                }
                else if (ftype === "backup") {
                    dgenies.run.reset_file_form("tab2", true);
                }
            }
            else {
                $(this).val("");
                dgenies.run.set_filename("", ftype);
                dgenies.notify(`File exceed the size limit (${max_file_size_txt})`, "danger", 2000);
                file_size.html("");
            }
        else {
            dgenies.run.set_filename("", ftype);
            file_size.html("");
        }
    });
};

/**
 * Initialise change source of file (local, url) event
 *
 * @param {string} ftype type of file (query, target, ...)
 * @private
 */
dgenies.run._set_file_select_event = function(ftype) {
    $(`select.${ftype}`).change(function() {
        dgenies.run.change_fasta_type(ftype, $(`select.${ftype}`).find(":selected").text().toLowerCase())
    });
};


/**
 * Change displayed tab
 *
 * @param {string} tab id of the tab to show
 */
dgenies.run.show_tab = function(tab) {
    $(`#tabs #${tab}`).addClass("active");
    $(`#tabs .tab:not(#${tab})`).removeClass("active");
    $(`.tabx:not(${tab})`).hide();
    $(`.tabx.${tab}`).show();
};


/**
 * Change displayed options (if any)
 *
 * @param {string} tool id to show
 */

dgenies.run.show_tool_options = function(tool) {
    $(`.optionx:not(tool-options-${tool})`).addClass("hidden");
    if($(`.optionx.tool-options-${tool}`).length > 1){
        $(`.optionx.tool-options-${tool}`).removeClass("hidden");
    }
};

/**
 * Initialise events
 */
dgenies.run.set_events = function() {
    let ftypes = ["query", "target", "alignfile", "queryidx", "targetidx", "backup", "batch"];
    $.each(ftypes, function (i, ftype) {
        dgenies.run._set_file_event(ftype);
        dgenies.run._set_file_select_event(ftype);
    });

    $("button#submit").click(function () {
        dgenies.run.submit();
    });
    $("button#example_align").click(function() {
        dgenies.run.fill_examples("tab1");
    });
    $("button#example_backup").click(function() {
        dgenies.run.fill_examples("tab2");
    });
    $("button#dl_backup").click(function() {
        window.location = "/example/backup"
    });
    $("button#example_batch").click(function() {
        dgenies.run.fill_examples("tab3");
    });

    $("button#view_batch").click(function() {
        $(this).find('a').click()
    });
    $("button#view_batch").find('a').click(function() {
        $(this).modal({
            showClose: false,
        });
        return false;
    });

    $("button#dl_batch").click(function() {
        window.location = "/example/batch"
    });

    $("#tabs .tab").click(function() {
        dgenies.run.show_tab($(this).attr("id"));
    });
    $("input[name=tool]").click(function() {
        dgenies.run.show_tool_options($(this).val());
    })
};

/**
 * Change source of fasta (local or url)
 *
 * @param {string} fasta type of fasta (query, target, ...)
 * @param {string} type source of fasta (local or url)
 * @param {boolean} keep_url if true, keep url in form, else empty it
 */
dgenies.run.change_fasta_type = function (fasta, type, keep_url=false) {
    let button = $("button#button-" + fasta);
    let input = $("input#" + fasta);
    let container = $("div." + fasta + "-label");
    $("input.file-" + fasta).val("");
    if (type === "local") {
        button.show();
        input.prop("readonly", true);
        input.val("");
        container.width(300);
    }
    else {
        button.hide();
        input.prop("readonly", false);
        if (!keep_url)
            input.val("");
        container.width(348);
    }
    $("div.file-size." + fasta).html("");
};

/**
 * Set filename for input fasta
 *
 * @param {string} name filename
 * @param {string} fasta type of fasta (query, target, ...)
 */
dgenies.run.set_filename = function (name, fasta) {
    $("input#" + fasta).val(name);
};

/**
 * Disable run form
 */
dgenies.run.disable_form = function () {
    dgenies.run.enabled = false;
    $("input, select, button").prop("disabled", true);
};

/**
 * Enable run form
 */
dgenies.run.enable_form = function () {
    $('.progress').find('.bar').css(
        'width', '0%'
    );
    $("input, select, button").prop("disabled", false);
    $("div#uploading-loading").hide();
    $("button#submit").show();
    let ftypes = ["query", "target", "targetidx", "queryidx", "alignfile", "backup", "batch"];
    for (let f in ftypes) {
        let ftype = ftypes[f];
        dgenies.run.hide_loading(ftype);
        dgenies.run.hide_success(ftype);
    }
    dgenies.run.files = [undefined, undefined, undefined, undefined, undefined, undefined, undefined];
    dgenies.run.restore_form();
    dgenies.run.enabled = true;
};

/**
 * Reset file input
 *
 * @param  {string}inp_name type of fasta (query, target, ...)
 */
dgenies.run.reset_file_input = function(inp_name) {
    dgenies.run.change_fasta_type(inp_name, $(`select.${inp_name}`).find(":selected").text().toLowerCase(), true);
    dgenies.run.files[dgenies.run.files_nb[inp_name]] = undefined;
};

/**
 * Reset all inputs in the given tab
 *
 * @param {string}  tab name
 * @param {boolean} except_backup if true, don't reset backup input
 */
dgenies.run.reset_file_form = function(tab, except_backup=false) {
    let ftypes = [];
    let i = 0;
    if ("tab2" === tab) {
        ftypes = ["alignfile", "queryidx", "targetidx"];
        if (!except_backup) {
            ftypes.push("backup");
        }
    }
    else if ("tab3" === tab) {
        ftypes = ["batch"];
    }
    else {
        ftypes = ["query", "target"];
    }
    $.each(ftypes, function(i, ftype) {
        dgenies.run.reset_file_input(ftype);
    });
};


/**
 * Do form submit staff (done once all uploads are done successfully)
 */
dgenies.run.do_submit = function () {
    let data = {
        "id_job": $("input#id_job").val(),
        "email": dgenies.mode === "webserver" ? $("input#email").val() : "",
        "s_id": dgenies.run.s_id
    };
    let jobs = [];
    let tab = $("#tabs .tab.active").attr("id");
    if (tab === "tab1") {
        data["type"] = "align";
        tool = $("input[name=tool]:checked").val()
        jobs.push(Object.assign({}, data, {
            "query": $("input#query").val(),
            "query_type": $("select.query").find(":selected").text().toLowerCase(),
            "target": $("input#target").val(),
            "target_type": $("select.target").find(":selected").text().toLowerCase(),
            "tool": tool,
            "tool_options": $.map($(`input[name|='tool-options-${tool}']:checked`),
                                  function(element) {
                                      return $(element).val();
                                  })
        }));
    }
    else if (tab === "tab2") {
        data["type"] = "plot";
        jobs.push(Object.assign({}, data, {
            "alignfile": $("input#alignfile").val(),
            "alignfile_type": $("select.alignfile").find(":selected").text().toLowerCase(),
            "query": $("input#queryidx").val(),
            "query_type": $("select.queryidx").find(":selected").text().toLowerCase(),
            "target": $("input#targetidx").val(),
            "target_type": $("select.targetidx").find(":selected").text().toLowerCase(),
            "backup": $("input#backup").val(),
            "backup_type": $("select.backup").find(":selected").text().toLowerCase(),
        }));
    }
    else { // tab3
        data["type"] = "batch";
        jobs = dgenies.run.job_list
    }
    console.log(jobs)
    data = Object.assign({}, data, {
            "jobs": jobs,
            "nb_jobs" : jobs.length
        });
    $("div#uploading-loading").html("Submitting form...");
    console.log(data);
    dgenies.post("/launch_analysis",
        data,
        function (data, status) {
            if (data["success"]) {
                window.location = data["redirect"];
            }
            else {
                if (dgenies.run.ping_interval !== null) {
                    clearInterval(dgenies.run.ping_interval);
                    dgenies.run.ping_interval = null;
                }
                if ("errors" in data) {
                    for (let i = 0; i < data["errors"].length; i++) {
                        dgenies.notify(data["errors"][i], "danger", 3000);
                    }
                }
                else {
                    dgenies.notify("An error has occurred. Please contact the support", "danger", 3000);
                }
                dgenies.run.enable_form();
            }
        }
        );
};

/**
 * Add an error to the form
 *
 * @param {string} error error message to display
 */
dgenies.run.add_error = function (error) {
    $("div.errors-submit ul.flashes").append($("<li>").append(error));
    dgenies.run.valid = false;
};

/**
 * Validate form
 *
 * @returns {boolean} true if form is valid, else false
 */
dgenies.run.valid_form = function () {
    let has_errors = false;

    // Check name:
    if ($("input#id_job").val().length === 0) {
        $("label.id-job").addClass("error");
        dgenies.run.add_error("Name of your job is required!");
        has_errors = true;
    }

    // Check mail:
    if (dgenies.mode === "webserver") {
        let email = $("input#email").val();
        let mail_re = /^.+@.+\..+$/;
        if (email.match(mail_re) === null) {
            $("label.email").addClass("error");
            if (email === "")
                dgenies.run.add_error("Email is required!");
            else
                dgenies.run.add_error("Email is not correct!");
            has_errors = true;
        }
    }

    let tab = $("#tabs .tab.active").attr("id");

    /* TAB 1 */
    if (tab === "tab1") {
        //Check input target:
        if ($("input#target").val().length === 0) {
            $("label.file-target").addClass("error");
            dgenies.run.add_error("Target fasta is required!");
            has_errors = true;
        }

        //Check input query:
        let tool = $("input[name=tool]:checked").val();
        if (!dgenies.run.tool_has_ava[tool] && $("input#query").val().length === 0) {
            $("label.file-query").addClass("error");
            dgenies.run.add_error("Query fasta is required!");
            has_errors = true;
        }
    }

    /* TAB 2 */
    else if (tab === "tab2")  {
        if ($("input#backup").val().length !== 0) {
            dgenies.run.reset_file_form("tab2", true);
        }
        else {
            if ($("input#targetidx").val().length === 0) {
                $("label.file-targetidx").addClass("error");
                dgenies.run.add_error("Target file is required!");
                has_errors = true;
            }
            if ($("input#alignfile").val().length === 0) {
                $("label.file-align").addClass("error");
                dgenies.run.add_error("Alignment file is required!");
                has_errors = true;
            }
        }
    }

    /* TAB 3 */
    else {
        //Check input target:
        let has_batch_error = false
        for (error of dgenies.run.batch_errors) {
            has_batch_error = has_batch_error || error.severity == "error"
        }
        if (has_batch_error) {
            dgenies.run.add_error("Batch file is incorrect");
            has_errors = has_batch_error
        }
        // Check that no file in batch file is missing
        if (dgenies.run.missing_files.length > 0) {
            dgenies.run.add_error("Some input files from batch file are missing!");
            has_errors = true;
        }
        // Check that no file in multiple upload field is duplicated
        if (dgenies.run.file_states.some((element) => element === "duplicated")) {
            dgenies.run.add_error("Some input files are duplicated!");
            has_errors = true;
        }
    }

    // Returns
    return !has_errors;
};

/**
 * Show loading for a fasta uploading file
 *
 * @param {string} fasta uploading file type (query, target, ...)
 */
dgenies.run.show_loading = function(fasta) {
    $(".loading-file." + fasta).show();
};

/**
 * Hide loading for a fasta uploaded file
 *
 * @param {string} fasta uploaded file type (query, target, ...)
 */
dgenies.run.hide_loading = function(fasta) {
    $(".loading-file." + fasta).hide();
};

/**
 * Show success: file uploaded successfully
 *
 * @param {string} fasta uploaded type of file (query, target, ...)
 */
dgenies.run.show_success = function(fasta) {
    $(".upload-success." + fasta).show()
};

/**
 * Hide success on a file
 *
 * @param {string} fasta type of file (query, target, ...)
 */
dgenies.run.hide_success = function(fasta) {
    $(".upload-success." + fasta).hide()
};

/**
 * Remove all errors displayed
 */
dgenies.run.reset_errors = function() {
    $("label").removeClass("error");
    $("div.errors-submit ul.flashes").find("li").remove();
    dgenies.run.valid = true;
};

/**
 * Ask server to start uploads
 */
dgenies.run.ask_for_upload = function () {
    console.info("Ask for upload...");
    dgenies.post("/ask-upload",
    {
        "s_id": dgenies.run.s_id
    },
    function (data, status) {
        if (data["success"]) {
            let allow_upload = data["allowed"];
            if (allow_upload) {
                $("div#uploading-loading").html("Uploading files...");
                dgenies.run.ping_interval = window.setInterval(dgenies.run.ping_upload, 15000);
                dgenies.run.upload_next();
            }
            else {
                window.setTimeout(dgenies.run.ask_for_upload, 15000);
            }
        }
        else {
            dgenies.notify("message" in data ? data["message"] : "An error has occurred. Please contact the support", "danger", 3000);
        }
    }, undefined, false
    );
};

/**
 * Ping server: we still upload or wait for upload
 */
dgenies.run.ping_upload = function () {
    dgenies.post("/ping-upload",
        {
            "s_id": dgenies.run.s_id
        },
        function (data, status) {
        }
    );
};

/**
 * Check if an URL is valid
 *
 * @param {string} url the url to check
 * @param {boolean} with_example consider 'example://' as url 
 * @returns {boolean} true if valid, else false
 */
dgenies.run.check_url = function (url, with_example=true) {
    return url.startsWith("http://") || url.startsWith("https://") || url.startsWith("ftp://") ||
        (url.startsWith("example://") && with_example);
};

/**
 * Check upload stuff
 *
 * @param ftype type of file (query, target, ...)
 * @param fname fasta name
 * @param from_batch if file is from batch tab (true), else false
 * @private
 */
dgenies.run._has_upload = function(ftype, fname, is_multiple = false) {
    let has_uploads = false;
    if (! is_multiple) {
        let fasta_type = parseInt($(`select.${ftype}`).val());
        let fasta_val = $(`input#${ftype}`).val();
        if (fasta_type === 0 && fasta_val.length > 0) {
            $(`button#button-${ftype}`).hide();
            dgenies.run.show_loading(ftype);
            has_uploads = true;
        }
        else {
            dgenies.run.files[dgenies.run.files_nb[ftype]] = undefined;
            if (fasta_val !== "" && !dgenies.run.check_url(fasta_val)) {
                dgenies.run.add_error(`${fname} file: invalid URL`, "error");
                dgenies.run.enable_form();
                return false;
            }
        }
    } else {
        // missing and duplicated files were checked before
        if (dgenies.run.file_states.some((element) => element === "available")){
            has_uploads = true;
            // TODO: hide/deactivate delete buttons?
    
            // TODO: show progress bar.
        }
    }
    return has_uploads;
};

/**
 * Launch upload of files
 */
dgenies.run.start_uploads = function() {
    /* The upload logic is the following:
        - First, depending to the current active tab, we set the input field that will be used as upload sources
        - Second, we check if each entry and is either a file or an url. On failure of one, the upload is aborded.
          If everything is an url, nothing needs to be uploaded
        - Thrid, we ask for upload. The server will validate if upload is possible. It will manage the parallel upload.
          Client side will use Timers to reiterate upload demands. When no more files are needed to upload, the form will be submitted.
     */
    let has_uploads = false;
    let tab = $("#tabs .tab.active").attr("id");
    let inputs = [];
    if (tab === "tab1") {
        dgenies.run.reset_file_form("tab2");
        dgenies.run.reset_file_form("tab3");
        inputs = [["query", "Query", false], ["target", "Target", false]];
        dgenies.run.files_to_upload = dgenies.run.files;
    }
    else if (tab === "tab2") {
        dgenies.run.reset_file_form("tab1");
        dgenies.run.reset_file_form("tab3");
        inputs = [["queryidx", "Query", false], ["targetidx", "Target", false], ["alignfile", "Alignment", false], ["backup", "Backup", false]];
        dgenies.run.files_to_upload = dgenies.run.files;
    }
    else {
        dgenies.run.reset_file_form("tab1");
        dgenies.run.reset_file_form("tab2");
        // TODO add url checking?
        inputs = [["batch-multiple-files-upload", `File listing`, true]];
        dgenies.run.files_to_upload = []
        for (let i=0; i<dgenies.run.files_for_batch.length; i++){
            if (dgenies.run.file_states[i] === "available") {
                dgenies.run.files_to_upload.push(dgenies.run.files_for_batch[i])
            }
        } 
    }
    // We check if there is some files to upload
    console.log(dgenies.run.files_to_upload)
    $.each(inputs, function(i, input) {
        let test_has_uploads = dgenies.run._has_upload(input[0], input[1], input[2]);
        has_uploads = has_uploads || test_has_uploads;
    });
    if (dgenies.run.valid) {
        if (has_uploads) {
            $("div#uploading-loading").html("Asking for upload...");
            dgenies.run.ask_for_upload();
        }
        else {
            dgenies.run.upload_next();
        }
    }
    else {
        dgenies.run.valid = true;
    }
};

/**
 * Show global loading
 */
dgenies.run.show_global_loading = function () {
    $("button#submit").hide();
    $('button[id^="example"]').hide();
    $("div#uploading-loading").show();
};

/**
 * Submit form
 */
dgenies.run.submit = function () {
    dgenies.run.reset_errors();
    if (dgenies.run.valid_form()) {
        dgenies.run.disable_form();
        dgenies.run.show_global_loading();
        dgenies.run.start_uploads();
    }
};