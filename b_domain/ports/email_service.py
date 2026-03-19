from abc import ABC, abstractmethod


class AbstractEmailService(ABC):
    """Abstract base class for email services.

    Defines the contract for sending emails. Concrete implementations
    should integrate with specific providers (e.g., SMTP, SendGrid, SES).
    """

    @abstractmethod
    def send_mail(
            self,
            recipients: list[str],
            subject: str,
            body: str,
            is_html: bool = False
    ) -> None:
        """Send an email message.

        Args:
            recipients (list[str]): List of recipient email addresses.
            subject (str): Subject line of the email.
            body (str): Body content of the email.
            is_html (bool, optional): Whether the body is HTML formatted.
                Defaults to False.
        """
