from b_domain.entities.user import User, UserPrefs
from c_application.dtos.user_dtos import UserOutputDTO, UserPrefsInputDTO


class UserMapper:
    """Centralized mapper for User transformations.

    Decouples the User Domain Entity from the application Output DTOs.
    """

    @staticmethod
    def to_output(user: "User") -> UserOutputDTO:
        """Maps a User entity to a UserOutputDTO."""
        return UserOutputDTO(
            id=str(user.id),
            username=user.username,
            timezone=user.preferences.timezone,
            language=user.preferences.language,
        )

    @staticmethod
    def to_domain_prefs(dto: UserPrefsInputDTO) -> UserPrefs:
        """
        Converte o DTO de preferências para o Value Object UserPrefs.

        Utiliza os valores padrão do UserPrefs caso o DTO não forneça
        informações para campos específicos (útil para registros simplificados).
        """

        # Criamos um dicionário apenas com os campos que não são None no DTO
        # Isso permite que o UserPrefs use seus valores default do dataclass
        data = {k: v for k, v in dto.__dict__.items() if v is not None}

        # Se você quiser garantir transformações específicas (ex: normalizar strings)
        if "language" in data:
            data["language"] = data["language"].lower()

        if "timezone" in data:
            # Aqui você poderia validar se o timezone é um IANA válido
            pass

        return UserPrefs(**data)
