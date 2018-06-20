from dgenies.config_reader import AppConfigReader
from flask_mail import Mail, Message


class Mailer:

    """
    Send mail throw flask app
    """

    def __init__(self, app):
        """

        :param app: Flask app object
        :type app: Flask
        """
        self.app = app
        self.mail = Mail(app)
        self.config = AppConfigReader()
        # self.mail_status = config_reader.get_mail_status_sender()
        # self.mail_reply = config_reader.get_mail_reply()
        # self.mail_org = config_reader.get_mail_org()
        # self.disable = config_reader.get_disable_mail()

    def _send_async_email(self, msg):
        """
        Send mail asynchronously

        :param msg: message to send
        :type msg: Message
        """
        with self.app.app_context():
            self.mail.send(msg)

    def send_mail(self, recipients, subject, message, message_html=None):
        """
        Send mail

        :param recipients: list of recipients
        :type recipients: list
        :param subject: mail subject
        :type subject: str
        :param message: message (text)
        :type message: str
        :param message_html: message (html)
        :type message_html: str
        """
        sender = (self.config.mail_org, self.config.mail_status_sender) if self.config.mail_org is not None else \
            self.config.mail_status_sender
        reply = self.config.mail_reply
        if not self.config.disable_mail:
            msg = Message(
                subject= subject,
                recipients=recipients,
                html=message_html,
                body=message,
                sender=sender,
                reply_to=reply
            )
            self._send_async_email(msg)
        else:  # Print debug
            print("################\n"
                  "# WARNING !!!! #\n"
                  "################\n\n"
                  "!!! SEND MAILS DISABLED BY CONFIGURATION !!!\n\n"
                  "(This might be disabled in production)\n\n")
            print("Sender: %s <%s>\n" % sender if isinstance(sender, tuple) else ("None", sender))
            print("Reply to: %s\n" % reply)
            print("Recipients: %s\n" % ", ".join(recipients))
            print("Subject: %s\n" % subject)
            print("Message:\n%s\n\n" % message)
            print("Message HTML:\n%s\n\n" % message_html)
