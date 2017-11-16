from config_reader import AppConfigReader
from flask_mail import Mail, Message


class Mailer:

    def __init__(self, app):
        self.app = app
        self.mail = Mail(app)
        config_reader = AppConfigReader()
        self.mail_status = config_reader.get_mail_status_sender()
        self.mail_reply = config_reader.get_mail_reply()
        self.mail_org = config_reader.get_mail_org()
        self.disable = config_reader.get_disable_mail()

    def __send_async_email(self, msg):
        with self.app.app_context():
            self.mail.send(msg)

    def send_mail(self, recipients: list, subject: str, message: str, message_html: str=None):
        sender = (self.mail_org, self.mail_status) if self.mail_org is not None else self.mail_status
        reply = self.mail_reply
        if not self.disable:
            msg = Message(
                subject= subject,
                recipients=recipients,
                html=message_html,
                body=message,
                sender=sender,
                reply_to=reply
            )
            self.__send_async_email(msg)
        else:  # Print debug
            print("################\n"
                  "# WARNING !!!! #\n"
                  "################\n\n"
                  "!!! SEND MAILS DISABLED BY CONFIGURATION !!!\n\n"
                  "(This might be disabled in production)\n\n")
            print("Sender: %s <%s>\n" % sender)
            print("Reply to: %s\n" % reply)
            print("Recipients: %s\n" % ", ".join(recipients))
            print("Subject: %s\n" % subject)
            print("Message:\n%s\n\n" % message)
            print("Message HTML:\n%s\n\n" % message_html)
