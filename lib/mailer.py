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

    def __send_async_email(self, msg):
        with self.app.app_context():
            self.mail.send(msg)

    def send_mail(self, recipients: list, subject: str, message: str, message_html: str=None):
        msg = Message(
            subject= subject,
            recipients=recipients,
            html=message_html,
            body=message,
            sender=(self.mail_org, self.mail_status) if self.mail_org is not None else self.mail_status,
            reply_to=self.mail_reply
        )
        self.__send_async_email(msg)
