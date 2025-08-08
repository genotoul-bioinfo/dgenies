# API

## Get instance configuration

```
GET /api/v1/config
```

## Submit a job

First submit a job with a post request

```
POST /api/v1/job
```

- if `batch_id` is not null, then the job has been submitted and no files are needed to be uploaded
- else, files need to be uploaded (list is in the `needed_files` array:
  - if `allowed_upload: False`, client must use `POST /api/v1/ask-upload` with session_id each 15s until the answer contains `allowed: True`
  - when `allowed_upload: True` or `allowed: True`, client can use `POST /api/v1/upload`:
    - until the response contains a no null `batch_id`, files must be uploaded. List of remaining files is in `needed_files` array

```mermaid
---
title: Submit Job (no local file)
---
sequenceDiagram
    Client ->> Server: POST /api/v1/job
    Server -->> Client: {allowed_upload: False, batch_id="<batch_id>", job_ids=[<job_id1>, ...], needed_files: [], session_id=null}
    Client ->> Server: GET /api/v1/status/<batch_id>
    Server -->> Client: { ... }
```

- Job with local files to upload

```mermaid
---
title: Submit Job (no local file)
---
sequenceDiagram
    Client ->> Server: POST /api/v1/job
    activate Server
    Server -->> Client: {allowed_upload: True|False, batch_id=null, job_ids=null, needed_files: [<filename1>, ..., <filenameN>], session_id=<sid>}
    loop while allowed_upload = False
        Client ->> Server: POST /api/v1/ask-upload {session_id: <sid>}
        Server -->> Client: {allowed: True|False}
    end
    activate Client
    par ping-upload
        loop Every 15s
            Client ->> Server: POST /api/v1/ping-upload {session_id=<sid>}
            Server -->> Client: {}
        end
    and upload
        loop for each fileX from <file1> to <fileN-1>
        Client ->>+ Server: POST /api/v1/upload {session_id=<sid>, file: <fileX>, ...}
        Server -->>- Client: {batch_id=null, file="<sanitized-filenameX>", job_ids=null, needed_files: [<filenameX+1>]}
        end
        Client ->>+ Server: POST /api/v1/upload {file: <fileN>, ...}
        Note right of Client: List file upload (<fileN>)
        Server -->>- Client: {batch_id="<batch_id>", file="<sanitized-filename2>", job_ids=[<job_id1>, ...], needed_files: []}

    end
    deactivate Client
    deactivate Server
    Client ->> Server: GET /api/v1/status/<batch_id>
    Server -->> Client: { ... }
```
