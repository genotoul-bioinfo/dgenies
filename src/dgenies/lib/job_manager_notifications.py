import os
from datetime import datetime
import re
from jinja2 import Template
from hashlib import sha1
from pathlib import Path
from urllib import request, parse
from urllib.error import URLError

from dgenies import MODE
from dgenies.database import Job
from .functions import Functions


class JobManagerNotificationsMixin:

    def get_job_mail_part(self, status, target_name, query_name=None):
        """
        Build mail content part for status mail for standard job

        :param status: job status
        :type status: str
        :param target_name: name of target
        :param target_name: name of target
        :type target_name: str
        :param query_name:  name of query
        :type query_name: str
        :return: mail content part
        :rtype: str
        """
        if status == "success":
            message = "Your job %s was completed successfully!\n\n" % self.id_job
            message += str("Your job {0} is finished. You can see the results by clicking on the link below:\n"
                           "{1}/result/{0}\n\n").format(self.id_job, self.config.web_url)
        else:
            message = "Your job %s has failed!\n\n" % self.id_job
            if self.error != "":
                message += self.error.replace("#ID#", self.id_job).replace("<br/>", "\n")
                message += "\n\n"
            else:
                message += "Your job %s has failed. You can try again. " \
                           "If the problem persists, please contact the support.\n\n" % self.id_job
            if os.path.exists(self.logs):
                message += str("For more details, you can check the logs file:\n"
                               "{1}/logs/{0}\n\n".format(self.id_job, self.config.web_url))

        if target_name is not None:
            message += "Sequences compared in this analysis:\n"
            if query_name is not None:
                message += "Target: %s\nQuery: %s\n\n" % (target_name, query_name)
            else:
                message += "Target: %s\n\n" % target_name
        if status == "success":
            if self.is_target_filtered():
                message += str("Note: target fasta has been filtered because it contains too small contigs."
                               "To see which contigs has been removed from the analysis, click on the link below:\n"
                               "{1}/filter-out/{0}/target\n\n").format(self.id_job, self.config.web_url)
            if self.is_query_filtered():
                message += str("Note: query fasta has been filtered because it contains too small contigs."
                               "To see which contigs has been removed from the analysis, click on the link below:\n"
                               "{1}/filter-out/{0}/query\n\n").format(self.id_job, self.config.web_url)
        return message

    def get_batch_mail_part(self, status):
        """
        Build mail content part for status mail for batch job

        :param status: job status
        :type status: str
        :return: mail content part
        :rtype: str
        """
        if status == "success":
            message = "Your batch job %s was completed successfully!\n\n" % self.id_job
        else:
            message = "Your batch job %s has failed!\n\n" % self.id_job
            if self.error != "":
                message += self.error.replace("#ID#", self.id_job).replace("<br/>", "\n")
                message += "\n\n"
            else:
                message += "Your job %s has failed. You can try again. " \
                           "If the problem persists, please contact the support.\n\n" % self.id_job
        message += "Here the detail of each job:\n\n"
        subjobs = (type(self)(i) for i in self.get_subjob_ids())
        for sj in subjobs:
            message += sj.id_job + "\n" + "-" * len(sj.id_job) + "\n\n"
            query_name, target_name = sj._get_query_target_names()
            message += sj.get_job_mail_part(sj.status().get("status", "unknown"), target_name, query_name)
        return message

    def get_mail_content(self, status, target_name, query_name=None):
        """
        Build mail content for status mail

        :param status: job status
        :type status: str
        :param target_name: name of target
        :type target_name: str
        :param query_name:  name of query
        :type query_name: str
        :return: mail content
        :rtype: str
        """
        message = "D-Genies\n\n"
        if self.is_batch():
            message += self.get_batch_mail_part(status)
        else:
            message += self.get_job_mail_part(status, target_name, query_name)
        message += "-------------------------\n"
        message += "See you soon on D-Genies,\n"
        message += "The D-Genies team"
        return message

    def get_mail_content_html(self, status, target_name, query_name=None):
        """
        Build mail content as HTML

        :param status: job status
        :type status: str
        :param target_name: name of target
        :type target_name: str
        :param query_name:  name of query
        :type query_name: str
        :return: mail content (html)
        :rtype: str
        """
        if self.is_batch():
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates",
                                   "batch_job_notification.html")) \
                    as t_file:
                template = Template(t_file.read())
                subjobs = (type(self)(i) for i in self.get_subjob_ids())
                subjob_list = []
                for sj in subjobs:
                    query_name, target_name = sj._get_query_target_names()
                    subjob_list.append({
                        "job_name": sj.id_job,
                        "status": sj.status().get("status", "unknown"),
                        "query_name": query_name if query_name is not None else "",
                        "target_name": target_name if target_name is not None else "",
                        "error": sj.error,
                        "has_logs": os.path.exists(sj.logs),
                        "target_filtered": sj.is_target_filtered(),
                        "query_filtered": sj.is_query_filtered()
                    })
                return template.render(job_name=self.id_job, status=status, url_base=self.config.web_url,
                                       error=self.error, subjobs=subjob_list)
        else:
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates",
                                   "job_notification.html")) \
                    as t_file:
                template = Template(t_file.read())
                return template.render(job_name=self.id_job, status=status, url_base=self.config.web_url,
                                       query_name=query_name if query_name is not None else "",
                                       target_name=target_name if target_name is not None else "",
                                       error=self.error, has_logs=os.path.exists(self.logs),
                                       target_filtered=self.is_target_filtered(),
                                       query_filtered=self.is_query_filtered())

    def get_mail_subject(self, status):
        """
        Build mail subject

        :param status: job status
        :type status: str
        :return: mail subject
        :rtype: str
        """

        if status == "success" or status == "no-match":
            return "DGenies - Job completed: %s" % self.id_job
        else:
            return "DGenies - Job failed: %s" % self.id_job

    def set_send_mail(self, activate):
        """
        Set or unset the ability to send mail for the current job

        :param activate: activate send mail if true, deactivate if false
        :type activate: bool
        """
        no_mail_file = os.path.join(self.output_dir, ".no_mail")
        if activate:
            if os.path.exists(no_mail_file):
                os.remove(no_mail_file)
        else:
            Path(no_mail_file).touch()

    def is_send_mail_allowed(self):
        """
        Set or unset the ability to send mail for the current job

        :return: True is sending a mail is allowed, False else
        :rtype: bool
        """
        return MODE == "webserver" and self.config.send_mail_status \
               and not os.path.exists(os.path.join(self.output_dir, ".no_mail"))

    def send_mail_if_allowed(self):
        """
        Send mail
        """
        if self.is_send_mail_allowed():
            # Retrieve infos:
            with Job.connect():
                job = Job.get(Job.id_job == self.id_job)
                if self.email is None:
                    self.email = job.email
                status = job.status
                self.error = job.error
                query_name, target_name = self._get_query_target_names()

                # Send:
                self.mailer.send_mail(recipients=[self.email],
                                      subject=self.get_mail_subject(status),
                                      message=self.get_mail_content(status, target_name, query_name),
                                      message_html=self.get_mail_content_html(status, target_name, query_name))

    def send_mail_post_if_allowed(self):
        """
        Send mail using POST url (if there is no access to mailer like on cluster nodes)
        """
        if self.is_send_mail_allowed():
            key = Functions.random_string(15)
            key_file = os.path.join(self.config.app_data, self.id_job, ".key")
            with open(key_file, "w") as k_f:
                k_f.write(key)
            data = parse.urlencode({"key": key}).encode()
            req = request.Request(self.config.send_mail_url + "/send-mail/" + self.id_job, data=data)
            self.logger.debug("{} - Sending mail: {} {} ".format(self.id_job, req.get_method(), req.get_full_url()))
            try:
                resp = request.urlopen(req)
                if resp.getcode() != 200:
                    self.logger.error("{} - Send mail failed!".format(self.id_job))
            except URLError as e:
                self.logger.error("{} - Send mail failed!".format(self.id_job))
                self.logger.error(e)

    def _anonymize_mail_client(self, email):
        """
        Replace the email address with its group defined in config file if anonymization is enabled
        :param email: email to anonymize
        :type email: str
        :return: email group if anonymization is enabled (empty string if no group matching), email else
        :rtype: str
        """
        if not self.config.disable_anonymous_analytics:
            return email
        if self.config.anonymous_analytics == "full_hash":
            return sha1(email.encode('utf-8')).hexdigest()
        if self.config.anonymous_analytics in ["dual_hash", "left_hash"]:
            lpart, rpart = email.rsplit('@', 1)
            return sha1(lpart.encode('utf-8')).hexdigest() + "@" + \
                   (sha1(
                       rpart.encode('utf-8')).hexdigest() if self.config.anonymous_analytics == "dual_hash" else rpart)
        else:
            for group, pattern in self.config.analytics_groups:
                if re.match(pattern, email):
                    return group
        return ''

    def _save_analytics_data(self):
        """
        Save analytics data into the database
        """
        if self.config.analytics_enabled and MODE == "webserver":
            from dgenies.database import Analytics
            with Job.connect():
                job = Job.get(Job.id_job == self.id_job)
                target_size = os.path.getsize(self.target.get_path()) if (self.target is not None and self.target.get_type()
                                                                          == "local" and
                                                                          os.path.exists(self.target.get_path())) else 0
                query_size = None
                if self.query is not None and self.query.get_type() == "local" and os.path.exists(self.query.get_path()):
                    query_size = os.path.getsize(self.query.get_path())
                log = Analytics.create(
                    id_job=self.id_job,
                    date_created=datetime.now(),
                    target_size=target_size,
                    query_size=query_size,
                    mail_client=self._anonymize_mail_client(job.email),
                    runner_type=job.runner_type,
                    job_type=self.get_job_type(),
                    tool=self.tool_name if self.tool_name is not None else "unset")
                log.save()

    def _set_analytics_job_status(self, status):
        """
        Change status for a job in analytics database

        :param status: new status
        :type status: str (20)
        """
        if self.config.analytics_enabled and MODE == "webserver":
            from dgenies.database import Analytics
            with Job.connect():
                analytic = Analytics.get(Analytics.id_job == self.id_job)
                if analytic.status != "no-match":
                    analytic.status = status
                    analytic.save()
