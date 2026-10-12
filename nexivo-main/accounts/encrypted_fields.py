"""
Model mixin that auto-encrypts designated fields on save and provides
decrypted property accessors. Applied to HostProfile to protect NIN and
bank account numbers stored in the database.
"""

from core.encryption import decrypt, encrypt


class EncryptedFieldsMixin:
    """
    Subclass this alongside models.Model and set ENCRYPTED_FIELDS = [...field names...].
    The mixin intercepts save() to encrypt and adds decrypt_<field> properties.
    """

    ENCRYPTED_FIELDS: list[str] = []

    def save(self, *args, **kwargs):
        for field in self.ENCRYPTED_FIELDS:
            raw = getattr(self, field, None)
            if raw is not None:
                setattr(self, field, encrypt(str(raw)))
        super().save(*args, **kwargs)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for field in getattr(cls, "ENCRYPTED_FIELDS", []):
            def make_property(f):
                def getter(self):
                    return decrypt(getattr(self, f))
                return property(getter)
            setattr(cls, f"decrypted_{field}", make_property(field))
