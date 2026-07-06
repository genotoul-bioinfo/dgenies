from __future__ import annotations

import logging


class DataFileContext:
    """
    Keep track of datafile context
    """

    def __init__(self, job, job_type: str, file_role: str, size_limit: int):
        self.job = job
        self.job_type = job_type
        self.file_role = file_role
        self.size_limit = size_limit

    def clone(self):
        return DataFileContext(self.job, self.job_type, self.file_role, self.size_limit)

    def __repr__(self):
        rep = ', '.join(['{}:{}'.format(k, v) for k, v in {'job': self.job, 'job_type': self.job_type,
                                                           'file_role': self.file_role, 'size_limit': self.size_limit}.items()])
        return 'DataFileContext({})'.format(rep)

    def __str__(self):
        return self.__repr__()


class DataFileContextManager:
    """
    Manage Datafile contexts
    """

    def __init__(self, jobs):
        """
        Create list of DatafilesContext for each Datafile in jobs
        """
        self.logger = logging.getLogger(__name__)
        self.datafile_dict = dict()
        for j in jobs:
            job_type = j.get_job_type()
            for file_role, datafile in j.get_datafiles():
                size_limit = j.get_file_size_for_role(file_role)
                dc = DataFileContext(job=j, job_type=job_type, file_role=file_role, size_limit=size_limit)
                self.add(datafile, dc)

    def add(self, datafile, context):
        """
        Remove datafile matching attribute from datafile context manager. Datafile is removed if it has no more context
        """
        try:
            self.datafile_dict[datafile].append(context)
        except KeyError:
            self.datafile_dict[datafile] = [context]

    def remove(self, datafile, **kwargs):
        """
        Remove datafile matching attribute from datafile context manager. Datafile is removed if it has no more context
        """
        to_remove, to_keep = [], []
        if datafile in self.datafile_dict:
            for ctx in self.datafile_dict[datafile]:
                if all([getattr(ctx, attr) == val for attr, val in kwargs.items()]):
                    to_remove.append(ctx)
                else:
                    to_keep.append(ctx)
            if to_keep:
                self.datafile_dict[datafile] = to_keep
            else:
                del self.datafile_dict[datafile]
        return to_remove

    def get_datafiles(self):
        return list(self.datafile_dict.keys())

    def get_distinct(self, datafile, *args):
        if datafile in self.datafile_dict:
            contexts = self.datafile_dict[datafile]
            return set(tuple(getattr(context, a) for a in args) for context in contexts)
        else:
            return set()

    def __repr__(self):
        return str([(datafile.get_path(), c) for datafile, contexts in self.datafile_dict.items() for c in contexts])

    def __str__(self):
        return self.__repr__()
