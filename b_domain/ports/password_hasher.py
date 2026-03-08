from typing import Protocol


class PasswordHasher(Protocol):
    """Contract for secure password hashing and verification.

    This port allows the domain to hash and verify passwords without
    depending on specific cryptographic libraries (like bcrypt or argon2).
    """

    def hash(self, password: str) -> str:
        """Hash a plaintext password securely.

        Args:
            password (str): The plaintext password.

        Returns:
            str: The resulting secure hash.
        """

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a stored hash.

        Args:
            plain_password (str): The plaintext password to check.
            hashed_password (str): The previously stored hash.

        Returns:
            bool: True if the password matches the hash, False otherwise.
        """
