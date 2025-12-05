import multiprocessing

proc_name = "dgenies"
# if we use socket to communicate with dgenies.
#bind = "unix:/run/dgenies-gunicorn.sock"
#bind = ['127.0.0.1:5000', '[::1]:5000']
bind = ['0.0.0.0:5000']
#workers = (2*multiprocessing.cpu_count()) + 1 #https://docs.gunicorn.org/en/stable/design.html#how-many-workers
workers = 2
threads = 2
worker_class = "gevent"

accesslog = "/logs/gunicorn.access.log"
errorlog = "/logs/gunicorn.error.log"

timeout = 120 # For huge load
#timeout = 480 # until nfs io problem are solved
raw_env = ["DISABLE_CRONS=True"] # Disable cron (will use systemd instead)
